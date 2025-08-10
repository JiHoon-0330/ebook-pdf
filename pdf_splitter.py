#!/usr/bin/env python3
"""
PDF 페이지 범위 추출 CLI 도구
특정 페이지 범위를 별도의 PDF로 생성
"""

import argparse
import sys
import subprocess
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
import PyPDF2
from PyPDF2 import PdfWriter, PdfReader
import curses

console = Console()


def open_folder(file_path: Path):
  """생성된 파일이 있는 폴더를 Finder에서 열기"""
  try:
    folder_path = file_path.parent
    subprocess.run(['open', str(folder_path)], check=True)
    console.print(f"[green]폴더가 열렸습니다: {folder_path}[/green]")
  except subprocess.CalledProcessError:
    console.print(f"[yellow]폴더 열기에 실패했습니다: {folder_path}[/yellow]")
  except Exception as e:
    console.print(f"[red]폴더 열기 중 오류: {e}[/red]")


def find_pdf_files(base_dir: Path = None) -> list[Path]:
  """PDF 파일들을 찾아서 반환"""
  if base_dir is None:
    base_dir = Path(__file__).resolve().parent

  # pdfs 폴더와 현재 폴더에서 PDF 찾기
  pdf_files = []

  # pdfs 폴더 확인
  pdfs_dir = base_dir / "pdfs"
  if pdfs_dir.exists():
    pdf_files.extend(pdfs_dir.glob("*.pdf"))

  # 현재 폴더 확인
  pdf_files.extend(base_dir.glob("*.pdf"))

  # 중복 제거 및 정렬
  pdf_files = sorted(list(set(pdf_files)))
  return pdf_files


def select_pdf_interactive(pdf_files: list[Path]) -> Path:
  """대화형으로 PDF 파일 선택"""
  if not pdf_files:
    console.print("[red]PDF 파일을 찾을 수 없습니다.[/red]")
    return None

  if len(pdf_files) == 1:
    console.print(f"[blue]PDF 파일이 1개 발견되어 자동 선택: {pdf_files[0].name}[/blue]")
    return pdf_files[0]

  # 테이블로 PDF 목록 표시
  table = Table(title="PDF 파일 목록")
  table.add_column("번호", style="cyan", width=6)
  table.add_column("파일명", style="green")
  table.add_column("크기", style="yellow", width=10)
  table.add_column("위치", style="blue")

  for i, pdf_file in enumerate(pdf_files, 1):
    try:
      size_mb = pdf_file.stat().st_size / (1024 * 1024)
      folder = "pdfs/" if "pdfs" in str(pdf_file) else "현재"
      table.add_row(
          str(i),
          pdf_file.name,
          f"{size_mb:.1f}MB",
          folder
      )
    except:
      table.add_row(str(i), pdf_file.name, "알 수 없음", "현재")

  console.print(table)

  while True:
    try:
      choice = Prompt.ask(f"PDF를 선택하세요 (1-{len(pdf_files)})", type=int)
      if 1 <= choice <= len(pdf_files):
        selected_pdf = pdf_files[choice - 1]
        console.print(f"[green]선택된 PDF: {selected_pdf.name}[/green]")
        return selected_pdf
      else:
        console.print(f"[red]1부터 {len(pdf_files)} 사이의 숫자를 입력하세요.[/red]")
    except (ValueError, KeyboardInterrupt):
      console.print("[yellow]선택이 취소되었습니다.[/yellow]")
      return None


def extract_pages(input_pdf: Path, output_pdf: Path, start_page: int, end_page: int) -> bool:
  """PDF에서 특정 페이지 범위를 추출하여 새로운 PDF 생성"""
  try:
    # PDF 파일 읽기
    with open(input_pdf, 'rb') as input_file:
      reader = PdfReader(input_file)
      total_pages = len(reader.pages)

      console.print(f"[blue]총 페이지 수: {total_pages}[/blue]")

      # 페이지 범위 검증
      if start_page < 1 or end_page > total_pages or start_page > end_page:
        console.print(
            f"[red]잘못된 페이지 범위입니다. (1-{total_pages} 범위 내에서 입력하세요)[/red]")
        return False

      # PDF 작성기 생성
      writer = PdfWriter()

      # 지정된 범위의 페이지들을 새 PDF에 추가
      for page_num in range(start_page - 1, end_page):  # 0-based index
        writer.add_page(reader.pages[page_num])
        console.print(f"[green]페이지 {page_num + 1} 추가[/green]")

      # 새 PDF 파일 저장
      with open(output_pdf, 'wb') as output_file:
        writer.write(output_file)

    console.print(f"[green]성공적으로 추출되었습니다: {output_pdf}[/green]")

    # 결과 정보 표시
    file_size_mb = output_pdf.stat().st_size / (1024 * 1024)
    extracted_pages = end_page - start_page + 1
    console.print(
        f"[blue]추출된 페이지: {extracted_pages}장 (페이지 {start_page}-{end_page})[/blue]")
    console.print(f"[blue]파일 크기: {file_size_mb:.2f} MB[/blue]")

    # 폴더 열기
    open_folder(output_pdf)

    return True

  except FileNotFoundError:
    console.print(f"[red]파일을 찾을 수 없습니다: {input_pdf}[/red]")
    return False
  except Exception as e:
    console.print(f"[red]PDF 처리 중 오류 발생: {e}[/red]")
    return False


def interactive_mode():
  """대화형 모드로 PDF 분할"""
  console.print(Panel.fit(
      "[bold blue]PDF 페이지 범위 추출 도구[/bold blue]\n"
      "PDF에서 원하는 페이지 범위를 별도 파일로 추출합니다.",
      title="대화형 모드"
  ))

  # PDF 파일 검색 및 선택
  pdf_files = find_pdf_files()
  input_pdf = select_pdf_interactive(pdf_files)

  if input_pdf is None:
    console.print("[yellow]PDF 선택이 취소되었습니다.[/yellow]")
    return

  # PDF 정보 확인
  try:
    with open(input_pdf, 'rb') as file:
      reader = PdfReader(file)
      total_pages = len(reader.pages)
      console.print(f"[blue]'{input_pdf.name}' - 총 {total_pages}페이지[/blue]")
  except Exception as e:
    console.print(f"[red]PDF 파일을 읽을 수 없습니다: {e}[/red]")
    return

  # 페이지 범위 입력
  while True:
    try:
      start_page = int(Prompt.ask(f"시작 페이지 (1-{total_pages})"))
      end_page = int(Prompt.ask(f"끝 페이지 ({start_page}-{total_pages})"))

      if 1 <= start_page <= end_page <= total_pages:
        break
      else:
        console.print(f"[red]올바른 범위를 입력하세요 (1-{total_pages})[/red]")
    except ValueError:
      console.print("[red]숫자를 입력하세요.[/red]")

  # 출력 파일명 자동 생성 (원본이름_시작페이지-끝페이지.pdf)
  output_pdf = input_pdf.parent / \
      f"{input_pdf.stem}_{start_page}-{end_page}.pdf"

  console.print(f"[blue]출력 파일: {output_pdf.name}[/blue]")

  # 파일 덮어쓰기 확인
  if output_pdf.exists():
    overwrite = Prompt.ask(
        f"'{output_pdf.name}' 파일이 이미 존재합니다. 덮어쓰시겠습니까?",
        choices=["y", "n"],
        default="n"
    )
    if overwrite.lower() != 'y':
      console.print("[yellow]작업을 취소했습니다.[/yellow]")
      return

  # PDF 추출 실행
  success = extract_pages(input_pdf, output_pdf, start_page, end_page)

  if success:
    console.print(f"\n[green]✓ PDF 추출이 완료되었습니다![/green]")
  else:
    console.print(f"\n[red]✗ PDF 추출에 실패했습니다.[/red]")


def main():
  """메인 함수"""
  parser = argparse.ArgumentParser(
      description="PDF에서 특정 페이지 범위를 추출하여 별도 PDF 생성",
      formatter_class=argparse.RawDescriptionHelpFormatter,
      epilog="""
사용 예시:
  # 대화형 모드
  python pdf_splitter.py

  # CLI 모드
  python pdf_splitter.py input.pdf -s 10 -e 20 -o chapter2.pdf
  python pdf_splitter.py ebook.pdf --start 1 --end 5 --output intro.pdf
  
  # 단일 페이지 추출
  python pdf_splitter.py document.pdf -s 15 -e 15 -o page15.pdf
        """
  )

  parser.add_argument(
      'input',
      nargs='?',
      help='입력 PDF 파일 경로'
  )

  parser.add_argument(
      '-s', '--start',
      type=int,
      help='시작 페이지 번호 (1부터 시작)'
  )

  parser.add_argument(
      '-e', '--end',
      type=int,
      help='끝 페이지 번호'
  )

  parser.add_argument(
      '-o', '--output',
      help='출력 PDF 파일 경로'
  )

  parser.add_argument(
      '-i', '--interactive',
      action='store_true',
      help='대화형 모드로 실행'
  )

  args = parser.parse_args()

  # 대화형 모드 또는 인수가 부족한 경우
  if args.interactive or not args.input:
    interactive_mode()
    return

  # CLI 모드 검증
  if not all([args.input, args.start, args.end]):
    console.print("[red]CLI 모드에서는 입력 파일, 시작 페이지, 끝 페이지가 모두 필요합니다.[/red]")
    console.print("대화형 모드를 사용하려면 '-i' 옵션을 추가하세요.")
    parser.print_help()
    sys.exit(1)

  # 파일 경로 처리
  input_pdf = Path(args.input)
  if not input_pdf.exists():
    console.print(f"[red]입력 파일을 찾을 수 없습니다: {input_pdf}[/red]")
    sys.exit(1)

  if not input_pdf.suffix.lower() == '.pdf':
    console.print(f"[red]PDF 파일이 아닙니다: {input_pdf}[/red]")
    sys.exit(1)

  # 출력 파일명 생성 (원본이름_시작페이지-끝페이지.pdf)
  if args.output:
    output_pdf = Path(args.output)
  else:
    output_pdf = input_pdf.parent / \
        f"{input_pdf.stem}_{args.start}-{args.end}.pdf"

  # CLI 정보 표시
  console.print(Panel.fit(
      f"[bold blue]PDF 페이지 추출[/bold blue]\n"
      f"입력: {input_pdf.name}\n"
      f"출력: {output_pdf.name}\n"
      f"범위: 페이지 {args.start}-{args.end}",
      title="CLI 모드"
  ))

  # PDF 추출 실행
  success = extract_pages(input_pdf, output_pdf, args.start, args.end)

  if success:
    console.print(f"\n[green]✓ PDF 추출이 완료되었습니다![/green]")
    sys.exit(0)
  else:
    console.print(f"\n[red]✗ PDF 추출에 실패했습니다.[/red]")
    sys.exit(1)


if __name__ == "__main__":
  main()
