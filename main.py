#!/usr/bin/env python3
"""
eBook PDF Generator - macOS 앱 스크린샷을 PDF로 변환하는 CLI 프로그램
"""

import os
import hashlib
import subprocess
import time
from pathlib import Path
from typing import List, Optional
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt
from rich.panel import Panel
from PIL import Image
from reportlab.pdfgen import canvas
import Quartz
import curses
import locale
import unicodedata
try:
  # NSWorkspace / NSRunningApplication (AppKit)
  from AppKit import NSWorkspace, NSRunningApplication
except Exception:
  NSWorkspace = None
  NSRunningApplication = None

console = Console()

# 로케일 설정 (유니코드 한글 표시 깨짐 방지)
try:
  locale.setlocale(locale.LC_ALL, "")
except Exception:
  pass


class AppManager:
  def __init__(self):
    self.base_dir = Path(__file__).resolve().parent
    self.screenshots_dir = self.base_dir / "screenshots"
    self.screenshots_dir.mkdir(parents=True, exist_ok=True)

    # 시작 시 스크린샷 폴더 비우기
    self._clear_screenshots_folder()

    self.last_image_hash = None
    self.reached_duplicate = False
    # 타이밍 파라미터
    self.post_focus_delay_sec = 1.0
    self.post_key_delay_sec = 1.0
    self.page_load_delay_sec = 0.5  # 페이지 로딩 대기
    self.retry_interval_sec = 0.3
    # ROI 파라미터 (임시 해시용)
    self.roi_left_ratio = 0.2
    self.roi_top_ratio = 0.75
    self.roi_right_ratio = 0.8
    self.roi_bottom_ratio = 0.98

  def get_running_apps(self) -> List[dict]:
    """실행 중인 앱 목록 (NSWorkspace 전용)"""
    if NSWorkspace is None:
      console.print("[red]NSWorkspace를 사용할 수 없습니다 (macOS 전용).[/red]")
      return []

    try:
      return self._get_running_apps_nsworkspace()
    except Exception as e:
      console.print(f"[red]NSWorkspace 조회 실패: {e}[/red]")
      return []

  def _get_running_apps_nsworkspace(self) -> List[dict]:
    """NSWorkspace 기반으로 실행 중인 앱 수집 (Swift 로직과 동일)"""
    apps: List[dict] = []
    workspace = NSWorkspace.sharedWorkspace()
    running_apps = workspace.runningApplications()

    seen_bundle_ids = set()

    for app in running_apps:
      bundle_id = app.bundleIdentifier()
      if not bundle_id:
        continue

      app_url = workspace.URLForApplicationWithBundleIdentifier_(bundle_id)
      if not app_url:
        continue

      original_path = app_url.path()
      if not original_path or not original_path.startswith('/Applications'):
        continue
      # 최상위 .app만 허용: /Applications/<App>.app 형태만 통과
      try:
        parent_dir = os.path.dirname(original_path)
      except Exception:
        parent_dir = None
      if parent_dir != '/Applications':
        continue

      app_name = app.localizedName() or 'Unknown'
      # 파일시스템(NFD)에서 온 한글을 NFC로 정규화하여 표시 깨짐 방지
      try:
        app_name = unicodedata.normalize('NFC', str(app_name))
      except Exception:
        app_name = str(app_name)
      pid = int(app.processIdentifier())

      if bundle_id in seen_bundle_ids:
        continue
      seen_bundle_ids.add(bundle_id)

      apps.append({
          'name': app_name,
          'bundle_id': bundle_id,
          'path': original_path,
          'pid': pid,
      })

    return apps

  def focus_app(self, bundle_id: str) -> bool:
    """앱에 포커스 주기 (더 안전한 방법)"""
    try:
      # 더 안전한 방법: open 명령어 사용
      subprocess.run([
          'open', '-b', bundle_id
      ], check=True)
      time.sleep(0.5)  # 앱이 활성화될 때까지 대기
      return True
    except subprocess.CalledProcessError:
      try:
        # 대체 방법: AppleScript 사용 (권한 필요할 수 있음)
        subprocess.run([
            'osascript', '-e',
            f'tell application id "{bundle_id}" to activate'
        ], check=True)
        time.sleep(0.5)
        return True
      except subprocess.CalledProcessError:
        return False

  def send_right_arrow(self) -> bool:
    """오른쪽 방향키를 전송하여 다음 페이지로 이동 (접근성 권한 필요할 수 있음)"""
    try:
      subprocess.run([
          'osascript', '-e',
          'tell application "System Events" to key code 124'
      ], check=True)
      time.sleep(0.05)
      return True
    except subprocess.CalledProcessError:
      # 폴백: Quartz 이벤트 전송 (전역)
      try:
        key_code = 124  # Right Arrow
        event_down = Quartz.CGEventCreateKeyboardEvent(None, key_code, True)
        event_up = Quartz.CGEventCreateKeyboardEvent(None, key_code, False)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event_down)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event_up)
        time.sleep(0.05)
        return True
      except Exception:
        return False

  def capture_screenshot(self, bundle_id: str, pid: Optional[int] = None) -> Optional[Path]:
    """선택한 앱의 최상위 보이는 창만 캡처 (CGWindowListCreateImage)
    bundle_id로 찾지 못하는 경우 제공된 PID로 폴백
    """
    try:
      # PID 결정: 우선 제공된 pid, 없으면 NSRunningApplication으로 조회
      target_pid: Optional[int] = None
      if pid is not None:
        target_pid = int(pid)
      else:
        if NSRunningApplication is None:
          console.print("[red]NSRunningApplication 사용 불가 (macOS 전용).[/red]")
          return None
        running_apps = NSRunningApplication.runningApplicationsWithBundleIdentifier_(
            bundle_id)  # type: ignore[attr-defined]
        target_app = running_apps.firstObject() if hasattr(
            running_apps, 'firstObject') else (running_apps[0] if running_apps else None)
        if target_app is None:
          console.print(
              f"[yellow]번들 ID로 실행 중인 앱을 찾지 못했습니다. PID 폴백을 사용합니다 (bundle: {bundle_id}).[/yellow]")
          if pid is None:
            return None
        else:
          target_pid = int(target_app.processIdentifier())
      if target_pid is None:
        console.print("[red]대상 PID를 확인할 수 없습니다.[/red]")
        return None

      # 윈도우 목록
      window_info_list = Quartz.CGWindowListCopyWindowInfo(
          Quartz.kCGWindowListOptionAll, Quartz.kCGNullWindowID)
      if not window_info_list:
        console.print("[red]윈도우 목록을 가져올 수 없습니다.[/red]")
        return None

      # 대상 PID + 화면에 보이는 창
      target_window_info = None
      for info in window_info_list:
        try:
          owner_pid = info.get(Quartz.kCGWindowOwnerPID, None)
          on_screen = bool(info.get(Quartz.kCGWindowIsOnscreen, False))
          if owner_pid == target_pid and on_screen:
            target_window_info = info
            break
        except Exception:
          continue

      if not target_window_info:
        console.print("[red]보이는 창을 찾지 못했습니다.[/red]")
        return None

      window_id = target_window_info.get(Quartz.kCGWindowNumber)
      if not window_id:
        return None

      image = Quartz.CGWindowListCreateImage(
          Quartz.CGRectNull,
          Quartz.kCGWindowListOptionIncludingWindow,
          window_id,
          Quartz.kCGWindowImageBestResolution | Quartz.kCGWindowImageBoundsIgnoreFraming,
      )

      if image is None:
        console.print("[red]이미지 생성 실패[/red]")
        self.reached_duplicate = False
        return None

      # 파일 저장(임시) 및 해시 측정
      timestamp = int(time.time())
      tmp_path = self.screenshots_dir / f"screenshot_{timestamp}_tmp.png"
      final_path = self.screenshots_dir / f"screenshot_{timestamp}.png"
      self.screenshots_dir.mkdir(parents=True, exist_ok=True)

      path_style = getattr(Quartz, 'kCFURLPOSIXPathStyle', 0)
      tmp_url = Quartz.CFURLCreateWithFileSystemPath(
          None,
          str(tmp_path),
          path_style,
          False,
      )
      dest_tmp = Quartz.CGImageDestinationCreateWithURL(
          tmp_url,
          "public.png",
          1,
          None,
      )
      if dest_tmp is None:
        raise RuntimeError("CGImageDestination 생성 실패")

      Quartz.CGImageDestinationAddImage(dest_tmp, image, None)
      if not Quartz.CGImageDestinationFinalize(dest_tmp):
        raise RuntimeError("CGImageDestinationFinalize 실패 (tmp)")

      if not tmp_path.exists():
        raise FileNotFoundError(f"임시 이미지 파일이 생성되지 않음: {tmp_path}")

      # 이미지 해시 비교 (pHash 사용으로 미세한 차이 무시)
      try:
        with Image.open(tmp_path) as img:
          current_phash = self._calculate_phash(img)
      except Exception:
        current_phash = None

      console.print(
          f"[blue]현재 pHash: {current_phash[:16] if current_phash else 'None'}..., 이전 pHash: {self.last_image_hash[:16] if self.last_image_hash else 'None'}...[/blue]")

      # pHash 해밍거리로 유사도 검사 (매우 유사하면 중복으로 간주)
      if self.last_image_hash and current_phash:
        distance = self._phash_distance(current_phash, self.last_image_hash)
        console.print(f"[blue]pHash 해밍거리: {distance} (임계값: 3)[/blue]")
        if distance <= 3:  # 매우 유사한 이미지
          console.print(
              "[yellow]매우 유사한 이미지입니다. 저장하지 않습니다.[/yellow]")
          tmp_path.unlink(missing_ok=True)
          self.reached_duplicate = True
          return None

      # 최종 파일명으로 이동
      tmp_path.rename(final_path)

      self.last_image_hash = current_phash if current_phash else self._calculate_image_hash(
          final_path)
      self.reached_duplicate = False
      console.print(f"[green]스크린샷이 저장되었습니다: {final_path}[/green]")
      return final_path

    except Exception as e:
      console.print(f"[red]스크린샷 캡처 실패: {e}")
      self.reached_duplicate = False
      return None

  def _capture_temp_hash(self, bundle_id: str, pid: Optional[int]) -> Optional[str]:
    """파일 저장 없이 현재 창의 ROI 퍼셉추얼 해시를 측정 (임시 파일 사용 후 제거)
    pHash는 렌더링 노이즈에 강하고, 작은 UI 변화에도 안정적.
    """
    try:
      timestamp = int(time.time() * 1000)
      temp_path = self.screenshots_dir / f"_probe_{timestamp}.png"
      # 임시 저장 후 해시 측정: 윈도우 이미지를 생성하여 temp에 저장
      # 윈도우 목록
      if NSRunningApplication is None:
        return None
      running_apps = NSRunningApplication.runningApplicationsWithBundleIdentifier_(
          bundle_id)  # type: ignore[attr-defined]
      target_app = running_apps.firstObject() if hasattr(
          running_apps, 'firstObject') else (running_apps[0] if running_apps else None)
      target_pid = int(target_app.processIdentifier()) if target_app is not None else (
          int(pid) if pid is not None else None)
      if target_pid is None:
        return None
      window_info_list = Quartz.CGWindowListCopyWindowInfo(
          Quartz.kCGWindowListOptionAll, Quartz.kCGNullWindowID)
      target_window_info = None
      for info in window_info_list or []:
        try:
          owner_pid = info.get(Quartz.kCGWindowOwnerPID, None)
          on_screen = bool(info.get(Quartz.kCGWindowIsOnscreen, False))
          if owner_pid == target_pid and on_screen:
            target_window_info = info
            break
        except Exception:
          continue
      if not target_window_info:
        return None
      window_id = target_window_info.get(Quartz.kCGWindowNumber)
      if not window_id:
        return None
      image = Quartz.CGWindowListCreateImage(
          Quartz.CGRectNull,
          Quartz.kCGWindowListOptionIncludingWindow,
          window_id,
          Quartz.kCGWindowImageBestResolution | Quartz.kCGWindowImageBoundsIgnoreFraming,
      )
      if image is None:
        return None
      path_style = getattr(Quartz, 'kCFURLPOSIXPathStyle', 0)
      file_url = Quartz.CFURLCreateWithFileSystemPath(
          None, str(temp_path), path_style, False)
      dest = Quartz.CGImageDestinationCreateWithURL(
          file_url, "public.png", 1, None)
      if dest is None:
        return None
      Quartz.CGImageDestinationAddImage(dest, image, None)
      if not Quartz.CGImageDestinationFinalize(dest):
        return None
      if not temp_path.exists():
        return None
      # ROI 추출 및 pHash 계산
      try:
        with Image.open(temp_path) as im:
          w, h = im.size
          left = int(w * self.roi_left_ratio)
          top = int(h * self.roi_top_ratio)
          right = int(w * self.roi_right_ratio)
          bottom = int(h * self.roi_bottom_ratio)
          if right <= left or bottom <= top:
            crop = im
          else:
            crop = im.crop((left, top, right, bottom))
          ph = self._calculate_phash(crop)
      except Exception:
        ph = None
      temp_path.unlink(missing_ok=True)
      return ph
    except Exception:
      return None

  def _get_frontmost_app(self) -> Optional[str]:
    """현재 포커스된 앱의 번들 ID 가져오기"""
    try:
      result = subprocess.run([
          'osascript', '-e',
          'id of application (path to frontmost application as text)'
      ], capture_output=True, text=True)

      if result.returncode == 0:
        return result.stdout.strip()
    except Exception:
      pass
    return None

  def _calculate_image_hash(self, image_path: Path) -> str:
    """이미지 해시 계산"""
    with open(image_path, 'rb') as f:
      return hashlib.md5(f.read()).hexdigest()

  def _calculate_phash(self, image: Image.Image) -> str:
    """64비트 퍼셉추얼 해시(pHash) 계산 (8x8 DCT 기반)"""
    # 1) 그레이스케일 변환 및 리사이즈(32x32)
    small = image.convert('L').resize((32, 32), Image.BICUBIC)
    pixels = list(small.getdata())
    # 2) 2D 배열로 변환
    matrix = [pixels[i * 32:(i + 1) * 32] for i in range(32)]
    # 3) DCT (간단한 구현)
    import math

    def dct_1d(vector):
      N = len(vector)
      result = [0.0] * N
      for k in range(N):
        s = 0.0
        for n in range(N):
          s += vector[n] * math.cos((math.pi / N) * (n + 0.5) * k)
        result[k] = s
      return result
    # 행 DCT
    dct_rows = [dct_1d(row) for row in matrix]
    # 열 DCT
    dct = [list(col) for col in zip(*[dct_1d(col) for col in zip(*dct_rows)])]
    # 4) 좌상단 8x8 저주파 성분 사용, DC 제외 평균 계산
    vals = []
    for y in range(8):
      for x in range(8):
        if x == 0 and y == 0:
          continue
        vals.append(dct[y][x])
    avg = sum(vals) / len(vals) if vals else 0
    # 5) 평균 대비 비트 생성 (64비트 문자열)
    bits = []
    for y in range(8):
      for x in range(8):
        if x == 0 and y == 0:
          bits.append('0')
          continue
        bits.append('1' if dct[y][x] > avg else '0')
    return ''.join(bits)

  def _phash_distance(self, a: Optional[str], b: Optional[str]) -> int:
    if not a or not b or len(a) != len(b):
      return 0
    return sum(ch1 != ch2 for ch1, ch2 in zip(a, b))

  def _clear_screenshots_folder(self):
    """스크린샷 폴더의 모든 파일 삭제"""
    try:
      deleted_count = 0
      for file_path in self.screenshots_dir.glob("*"):
        if file_path.is_file():
          file_path.unlink()
          deleted_count += 1
      if deleted_count > 0:
        console.print(f"[blue]이전 스크린샷 {deleted_count}개를 삭제했습니다.[/blue]")
    except Exception as e:
      console.print(f"[yellow]스크린샷 폴더 정리 중 오류: {e}[/yellow]")

  def _create_pdf(self):
    """저장된 이미지들을 고해상도 FHD PDF로 변환 (마지막 페이지 제외)"""
    try:
      image_files = sorted(self.screenshots_dir.glob("*.png"))
      if not image_files:
        console.print("[yellow]PDF로 변환할 이미지가 없습니다.[/yellow]")
        return

      # 마지막 페이지 제외 (최소 1장은 남겨두기)
      if len(image_files) > 1:
        image_files = image_files[:-1]
        console.print(
            f"[blue]마지막 페이지를 제외하고 {len(image_files)}장의 이미지로 PDF를 생성합니다.[/blue]")
      else:
        console.print("[blue]1장의 이미지로 PDF를 생성합니다.[/blue]")

      pdf_path = self.base_dir / "ebook.pdf"

      # 첫 번째 이미지로 최적 크기 계산
      first_image = image_files[0]
      with Image.open(first_image) as sample_img:
        original_width, original_height = sample_img.size

        # FHD 기준으로 적절한 크기 계산 (FHD보다 크지만 적당한 크기)
        fhd_width, fhd_height = 1920, 1080

        # 원본이 FHD보다 큰 경우만 축소
        if original_width > fhd_width or original_height > fhd_height:
          # 가로/세로 중 큰 쪽을 기준으로 FHD의 1.5배로 제한
          max_dimension = max(fhd_width, fhd_height) * 1.5  # 1620

          if original_width >= original_height:
            # 가로가 더 긴 경우
            scale_factor = max_dimension / original_width
          else:
            # 세로가 더 긴 경우
            scale_factor = max_dimension / original_height

          target_width = int(original_width * scale_factor)
          target_height = int(original_height * scale_factor)
        else:
          # 이미 FHD보다 작으면 원본 크기 유지
          target_width = original_width
          target_height = original_height

      page_width = target_width
      page_height = target_height
      page_size = (page_width, page_height)

      # 비율 계산
      ratio = target_width / target_height

      console.print(
          f"[blue]원본 크기: {original_width}x{original_height}[/blue]")
      console.print(
          f"[blue]PDF 페이지 크기: {page_width}x{page_height} 픽셀 (비율: {ratio:.2f})[/blue]")

      # ReportLab으로 원본 비율 유지 PDF 생성
      c = canvas.Canvas(str(pdf_path), pagesize=page_size)

      for i, image_file in enumerate(image_files):
        console.print(
            f"[green]고해상도 PDF 페이지 추가: {i+1}/{len(image_files)} - {image_file.name}[/green]")

        # 이미지를 FHD 크기로 직접 리사이즈하여 PDF에 추가
        with Image.open(image_file) as original_img:
          # RGB 변환
          if original_img.mode != 'RGB':
            original_img = original_img.convert('RGB')

          # 원본 비율 유지하면서 계산된 크기로 조정
          resized_img = original_img.resize(
              (target_width, target_height), Image.Resampling.LANCZOS)

          # 임시 파일 저장
          temp_path = self.screenshots_dir / f"temp_{i}.png"
          resized_img.save(temp_path, 'PNG')

          # PDF에 추가
          c.drawImage(
              str(temp_path),
              0, 0,
              width=page_width,
              height=page_height,
              preserveAspectRatio=False
          )

          # 임시 파일 삭제
          temp_path.unlink(missing_ok=True)

        if i < len(image_files) - 1:  # 마지막 페이지가 아니면 새 페이지 추가
          c.showPage()

      c.save()

      console.print(f"[green]최적화된 PDF가 생성되었습니다: {pdf_path}[/green]")

      # 파일 크기 확인
      file_size_mb = pdf_path.stat().st_size / (1024 * 1024)
      console.print(
          f"[blue]총 페이지 수: {len(image_files)}장, 파일 크기: {file_size_mb:.2f} MB[/blue]")
      console.print(
          f"[blue]각 페이지: {page_width}x{page_height} 픽셀 (비율: {ratio:.2f})[/blue]")

    except Exception as e:
      console.print(f"[red]최적화된 PDF 생성 실패: {e}[/red]")


class InteractiveAppSelector:
  def __init__(self, app_manager: AppManager):
    self.app_manager = app_manager
    self.selected_index = 0

  def display_apps(self, apps: List[dict]):
    """앱 목록을 테이블로 표시"""
    # 간단 출력: 앱 이름만 노출
    table = Table(title="실행 중인 앱 목록", show_header=False, box=None)
    table.add_column("앱 이름", style="green")
    for i, app in enumerate(apps):
      marker = "→ " if i == self.selected_index else "  "
      table.add_row(f"{marker}{app['name']}")
    console.print(table)
    console.print("\n[bold]조작법:[/bold]")
    console.print("↑/↓: 이동  |  Enter: 선택  |  q: 종료")

  def get_user_selection(self, apps: List[dict]) -> Optional[dict]:
    """사용자 선택 처리"""
    try:
      idx = curses.wrapper(self._curses_select, apps)
      if idx is None:
        return None
      self.selected_index = idx
      return apps[self.selected_index]
    except Exception:
      # 폴백: 번호 입력
      while True:
        console.clear()
        self.display_apps(apps)
        choice = Prompt.ask(
            "앱을 선택하세요 (번호 입력, q로 종료)",
            choices=[str(i) for i in range(len(apps))] + ['q']
        )
        if choice == 'q':
          return None
        else:
          self.selected_index = int(choice)
          return apps[self.selected_index]

  def _curses_select(self, stdscr, apps: List[dict]) -> Optional[int]:
    curses.curs_set(0)
    stdscr.nodelay(False)
    stdscr.keypad(True)
    selected = self.selected_index if apps else 0

    while True:
      stdscr.clear()
      header = "실행 중인 앱 (↑/↓ 이동, Enter 선택, q 종료)"
      try:
        stdscr.addstr(0, 0, header)
      except curses.error:
        pass

      for i, app in enumerate(apps):
        name = app['name']
        y = i + 2
        try:
          if i == selected:
            stdscr.attron(curses.A_REVERSE)
            stdscr.addstr(y, 2, name)
            stdscr.attroff(curses.A_REVERSE)
          else:
            stdscr.addstr(y, 2, name)
        except curses.error:
          # 화면을 넘어가는 경우 무시
          continue

      stdscr.refresh()
      key = stdscr.getch()

      if key in (curses.KEY_UP, ord('k')):
        selected = (selected - 1) % len(apps)
      elif key in (curses.KEY_DOWN, ord('j')):
        selected = (selected + 1) % len(apps)
      elif key in (curses.KEY_ENTER, 10, 13):
        return selected
      elif key in (ord('q'), 27):  # ESC or q
        return None


def main():
  """메인 함수"""
  console.print(Panel.fit(
      "[bold blue]eBook PDF Generator[/bold blue]\n"
      "macOS 앱 스크린샷을 PDF로 변환하는 프로그램",
      title="시작"
  ))

  app_manager = AppManager()
  selector = InteractiveAppSelector(app_manager)

  while True:
    # 실행 중인 앱 목록 가져오기
    apps = app_manager.get_running_apps()

    if not apps:
      console.print("[red]실행 중인 앱을 찾을 수 없습니다.[/red]")
      return

    # 사용자 선택
    selected_app = selector.get_user_selection(apps)
    if not selected_app:
      console.print("[yellow]프로그램을 종료합니다.[/yellow]")
      break

    # 앱에 포커스
    console.print(f"[blue]'{selected_app['name']}' 앱에 포커스를 줍니다...[/blue]")
    target_bundle_id = selected_app['bundle_id']
    target_pid = selected_app.get('pid')
    if not app_manager.focus_app(target_bundle_id):
      console.print(f"[red]'{selected_app['name']}' 앱에 포커스를 줄 수 없습니다.[/red]")
      continue

    # 자동 캡처-넘김 루프 (10번 연속 동일 이미지 시 PDF 생성)
    time.sleep(app_manager.post_focus_delay_sec)
    duplicate_count = 0
    max_duplicates = 10

    while True:
      # 현재 전면 앱이 선택한 앱이 아니면 중단
      frontmost = app_manager._get_frontmost_app()
      if frontmost and frontmost != target_bundle_id:
        console.print("[yellow]포커스가 다른 앱으로 변경되어 캡처를 중단합니다.[/yellow]")
        app_manager._create_pdf()
        break

      # 1) 페이지 로딩 완료 대기 (누락 방지)
      console.print("[blue]페이지 로딩을 기다립니다...[/blue]")
      time.sleep(app_manager.page_load_delay_sec)

      # 2) 현재 페이지 캡처
      console.print("[blue]페이지를 캡처합니다...[/blue]")
      shot = app_manager.capture_screenshot(target_bundle_id, pid=target_pid)

      # 3) 저장 확인 및 중복 체크
      if app_manager.reached_duplicate:
        # 동일 이미지 감지 (저장되지 않음)
        duplicate_count += 1
        console.print(
            f"[yellow]동일한 이미지입니다 ({duplicate_count}/{max_duplicates}). 저장하지 않습니다.[/yellow]")
        if duplicate_count >= max_duplicates:
          console.print("[green]10번 연속 동일 이미지로 캡처를 종료합니다.[/green]")
          app_manager._create_pdf()
          break
      elif shot is None:
        # 캡처 실패 시 재시도
        console.print("[yellow]캡처 실패, 재시도합니다.[/yellow]")
        time.sleep(app_manager.retry_interval_sec)
        continue
      else:
        # 새로운 이미지 저장됨
        duplicate_count = 0
        console.print(f"[green]새 페이지가 저장되었습니다: {shot}[/green]")

      # 4) 다음 페이지로 이동
      console.print("[blue]다음 페이지로 이동합니다...[/blue]")
      moved = app_manager.send_right_arrow()
      if not moved:
        console.print(
            "[yellow]방향키 전송에 실패했습니다. 접근성 권한을 확인하세요. 캡처를 종료합니다.[/yellow]")
        app_manager._create_pdf()
        break

      # 5) 페이지 전환 후 안정화 대기
      console.print("[blue]페이지 전환 후 안정화를 기다립니다...[/blue]")
      time.sleep(app_manager.post_key_delay_sec)


if __name__ == "__main__":
  main()
