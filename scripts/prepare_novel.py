#!/usr/bin/env python3
"""Split a Chinese novel into stable chapter files with source line mappings."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


CHAPTER_RE = re.compile(
    r"第([〇零一二三四五六七八九十百千两\d]+)章\s*(.*?)\s*$"
)
VOLUME_PREFIX_RE = re.compile(
    r"^第[〇零一二三四五六七八九十百千两\d]+[集卷部篇](?:\s+.*?)?$"
)
# Some compilations set chapter numbers in full-width digits (第４０６章). Fold them
# before matching so the heading is recognised; the stored chapter text is never
# touched, only the probe copy used for pattern matching.
FULLWIDTH_TRANS = str.maketrans("０１２３４５６７８９", "0123456789")
# 「正文 第1159 你还嫩了一点」「正文 第1161草章 袭击丽玲」: a real chapter heading whose
# 章 was lost or garbled, always carrying the 正文 marker. Without this the chapter
# disappears from the graph even though its text is present.
SALVAGE_HEADING_RE = re.compile(
    r"^正文\s*第([〇零一二三四五六七八九十百千两\d]+)\s*(?:[^\s\d\-—~至]{0,2}章)?\s*(.*)$"
)
# 「正文 第386-405」「正文 第411- 413章」: a section range marker, not a chapter. It
# must be rejected before SALVAGE_HEADING_RE, which would otherwise read 「-405」 as
# the title of a chapter 386.
SALVAGE_RANGE_RE = re.compile(r"^正文\s*第[〇零一二三四五六七八九十百千两\d]+\s*[-—~至]")
# A repeat of the immediately preceding heading (the 流氓老师 source repeats
# 「第1516章 奇怪的东西」 four lines later as 「第15章奇怪的东西…」 with the body merged
# onto the heading line) is a mangled copy, not a new chapter. Beyond this gap the
# repeat is a chapter whose number was garbled, and it gets renumbered instead.
MANGLED_HEADING_GAP = 20
PART_SUFFIX_RE = re.compile(r"\s*[（(][上中下〇零一二三四五六七八九十百千两\d]+[）)]\s*$")
# A heading-like first line of the front matter ("序章", "楔子 血月", "引子：...").
FRONT_HEADING_RE = re.compile(r"^(序章|序言|序幕|楔子|引子|前言|序)\s*[:：]?\s*(.*)$")
# A table-of-contents line: a title followed by dot leaders and a page number.
TOC_TAIL_RE = re.compile(r"[.．·…]{2,}\s*\d{1,4}\s*$")
# Ebook packaging wrapped around the text: 『书名/作者』, a status line, the blurb,
# promo URLs, and the 章节内容开始/结束 markers. The blurb is a whole-book summary,
# so keeping it in the graph would hand a pass the future information that
# chapter-scoped views exist to withhold.
PACKAGING_RE = re.compile(r"『[^』]*』|【[^】]*】|章节内容(开始|结束)|正文(开始|结束)|https?://")
SENTENCE_END_RE = re.compile(r"[。！？…”」』]")
DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3,
          "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
UNITS = {"十": 10, "百": 100, "千": 1000}


# Markers that identify ebook packaging or a publisher's blurb rather than story
# text. A 内容简介 is the whole book in three sentences, so including it as
# chapter 0 would put the ending in front of the reader on the first click — the
# exact future-information leak the chapter-scoped views exist to prevent.
PACKAGING_MARKERS = (
    "内容简介", "作品简介", "本书简介", "作者：", "作者:", "声明", "版权",
    "用户上传", "上传至", "电子书", "免费下载", "全集", "www.", "http",
    ".com", ".net", ".cn", "请勿",
)

# A pirated compilation interleaves its own furniture *inside* a chapter, not only
# around it: a bare `<divclass="contentadv">` line wedged between two paragraphs, a
# `<center>高速本站域名</center>show_yuedu3;` line, an `<ahref="http://...">` promo
# link, and a decimal-entity URL (`&#91;&#;&#;&#119;...&#93;`) spliced into the middle
# of a sentence. Front-matter trimming never sees these because they sit past the
# first heading, so they survive into the chapter text a later pass quotes from — and
# an entity-encoded promo URL can then be lifted into evidence verbatim.
INLINE_TAG_RE = re.compile(r"<[^>\n]{0,200}>")
HTML_ENTITY_RE = re.compile(r"&#x?[0-9A-Fa-f]*;")
BARE_URL_RE = re.compile(r"https?://|www\.[A-Za-z0-9]")
SITE_FURNITURE_RE = re.compile(
    r"本站域名|手机用户请浏览|请浏览阅读|更优质的阅读体验|contentadv|show_yuedu"
)

# 水印域名里的全角／异体写法：`www.1６ｋ.ｃＮ`、`www.⑴⑹κ.cn`、`www.16……ｋ.cn`、
# `http://WAP．bxwx．CN`。字符类必须把 CJK 排除在外——写成 `[^\s，。]*` 会把后面的
# 正文一起吃掉（`wWw.16K.Cn首发有办法的了` → 连「有办法的了」也当域名）。
_URL_CHARS = (
    "A-Za-z0-9"          # ASCII
    "０-９Ａ-Ｚａ-ｚ"      # 全角
    "⑴-⒇①-⑩κΚ"          # 圈码与希腊字母
    "．.。_/~:?？=&-"
)
WATERMARK_URL_RE = re.compile(
    rf"(?:https?://|www[．.]|wap[．.]|WAP．)[{_URL_CHARS}]{{2,}}", re.IGNORECASE
)
# 站点自述句。与 URL 无关时也独立出现（`16k小说`、`全文字阅读让您一目了然`），
# 所以单列一条，不能只靠 URL 命中来定位水印。末尾的句读一起吃掉，免得正文里
# 留下一个孤零零的「！」。
SITE_BLURB_RE = re.compile(
    r"本作品独家文字版首发[^。！？\n]{0,40}[。！？]?"
    r"|更多最新最快章节[^。！？\n]{0,24}[。！？]?"
    r"|全文字阅读让您一目了然"
    r"|本书转载"
    r"|(?:手机|电脑)(?:访问|用户请浏览|书友)"
    r"|l[6６]k手机书[：:]?|可以访问[：:]?"
    r"|1[6６l][ｋkK]小说|1[6６]K文学网|txt80\.com|bxwx|1[6６]Ｋ|1６K"
    # 「首发」本身是常用词（首发阵容、首发队员），**不能裸匹配**：2026-09-14 在斗罗
    # 实测 `|首发` 把正文「一直首发的七个人」删成了「一直的七个人」，并把
    # `ev_ch382_wang_qiuer_chuchang` 的引文变成不可定位。只在站点语境里删。
    r"|(?<=本站)首发|(?<=本书)首发|首发网站|首发地址"
)
SPACED_WATERMARK_RE = re.compile(r"(?:[^\s_]{1,2}[ _]+){5,}[^\s_]{0,2}")


def is_spaced_watermark(text: str) -> bool:
    """「把每个字符用空格或下划线拆开」的水印。

    `八 零 电 子 书 w w w . t x t 8 0. c o m` 与
    `㈧_ ○_電_芓_書_Ｗ_ w_ ω_.Τ_Χ_t_捌_０. c_Ο_Μ` 属于同一类。中文正文不逐字加空格，
    所以「被空格／下划线隔开的单字符占到多数」只可能是这种水印，不会误伤正文
    （正文按空格切出来的是长句，不是一堆单字）。
    """
    tokens = [t for t in re.split(r"[ _]+", text) if t]
    if len(tokens) < 6:
        return False
    singles = sum(1 for t in tokens if len(t) == 1)
    return singles >= len(tokens) * 0.6


def clean_inline_packaging(line: str) -> str:
    """Strip pirated-site furniture from one source line, keeping its newline.

    The line count must not change: `source_line_start`/`source_line_end` are source
    file line numbers, and `resolve_evidence.py` locates every quote by them. So a
    line that turns out to be pure furniture is blanked rather than deleted.

    Furniture is **excised, not blanked**. The sites splice their blurb into the
    middle or the end of a real paragraph:

        叶大伟见刘美琴没有喝茶，忙对她说道：“刘老师……请喝茶。”……他就要冲上前逼着她
        喝。本作品独家文字版首发，未经同意不得转载，摘编，更多最新最快章节，请访问
        www.bxwx.net！

    The earlier version blanked the whole line as soon as `BARE_URL_RE` matched
    anywhere in it, which deleted that paragraph outright — 155 chapters of this run
    lost prose to it (chapters/081.txt lost 「叶大伟见刘美琴没有喝茶…」 wholesale).
    Excising the watermark span leaves the sentence intact; only a line whose
    remainder carries no word character at all is a pure-furniture line and gets
    blanked.

    Only site furniture is removed. The author's own bracketed notes (【...】) are
    left alone on purpose — in this corpus they also carry real setting material
    (the 玄力 level table in ch1, the 星隐丹 description in ch33, the currency note in
    ch40), so dropping every 【】 line would delete world-building the graph needs.
    """
    cleaned = HTML_ENTITY_RE.sub("", INLINE_TAG_RE.sub("", line))
    if is_spaced_watermark(cleaned):
        return "\n" if line.endswith("\n") else ""
    cleaned = WATERMARK_URL_RE.sub("", cleaned)
    cleaned = SITE_BLURB_RE.sub("", cleaned)
    cleaned = SITE_FURNITURE_RE.sub("", cleaned)
    cleaned = SPACED_WATERMARK_RE.sub("", cleaned)
    if not re.search(r"[\w\u4e00-\u9fff]", cleaned):
        return "\n" if line.endswith("\n") else ""
    return cleaned


def looks_like_prose(text: str) -> bool:
    """Decide whether the block before the first numbered heading is narrative prose.

    Front matter is either a prologue — story that belongs in the graph — or a
    title page / table of contents / blurb, which does not. Both are text before
    the first `第N章`, so the difference has to be judged from the shape: prose has
    sentence-ending punctuation and mostly long lines, a table of contents has dot
    leaders and trailing page numbers.
    """
    if len(text) < 120:
        return False
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    toc_like = sum(1 for line in lines if TOC_TAIL_RE.search(line))
    if toc_like >= max(2, len(lines) // 3):
        return False
    if not SENTENCE_END_RE.search(text):
        return False
    long_lines = sum(1 for line in lines if len(line) >= 20)
    return long_lines >= max(1, len(lines) // 2)


def front_matter_title(lines: list[str]) -> str:
    """Use the block's own heading when it has one, otherwise a neutral label."""
    for line in lines:
        text = line.strip()
        if not text:
            continue
        if len(text) <= 20:
            match = FRONT_HEADING_RE.match(text)
            if match:
                return text
        break
    return "序章"


def trim_front_matter(lines: list[str]) -> tuple[list[str], int, int]:
    """Drop ebook packaging from the front-matter block, keeping the story.

    A scene-setter file commonly opens with 『书名/作者』, a status line, the blurb, a
    promo URL, and a `------章节内容开始-------` marker before the prologue heading.
    Starting at that heading is what separates the prologue from the packaging, and
    it keeps the blurb out of the graph. Returns the kept lines plus how many lines
    were dropped at each end, so the caller can map them back to source line numbers.
    """
    start = 0
    for index, line in enumerate(lines[:15]):
        text = line.strip()
        if len(text) <= 20 and FRONT_HEADING_RE.match(text):
            start = index
            break
    end = len(lines)
    while end > start and (not lines[end - 1].strip() or PACKAGING_RE.search(lines[end - 1])):
        end -= 1
    return lines[start:end], start, len(lines) - end


def chinese_number(value: str) -> int:
    if value.isdigit():
        return int(value)
    total = 0
    section = 0
    number = 0
    for char in value:
        if char in DIGITS:
            number = DIGITS[char]
        elif char in UNITS:
            unit = UNITS[char]
            if number == 0:
                number = 1
            section += number * unit
            number = 0
        else:
            raise ValueError(f"Unsupported Chinese numeral: {value}")
    total += section + number
    return total


def match_heading(probe: str) -> tuple[int, str, str] | None:
    """Parse a heading-shaped line into ``(chapter_no, title, prefix)``.

    ``probe`` must already have full-width digits folded to ASCII. Returns ``None``
    when the line is not a heading: too long, a table-of-contents entry, a section
    range marker, or carrying a prefix that is neither a volume nor the ``正文``
    marker. The ``正文`` marker is a section label, not a volume, so it is reported
    with an empty prefix.
    """
    if len(probe) > 120 or TOC_TAIL_RE.search(probe) or SALVAGE_RANGE_RE.match(probe):
        return None
    # 行内标签要先剥掉。这份源文件把每个章标题又用 <strong> 重写了一遍
    # （`<strong>第221章赞美</strong>`），不剥就认不出来：`第221章` 的两个出现
    # 位置，一处是「第220章我早有准备 第221章赞美」这一行（已被算作第220章的标题），
    # 另一处就是这种写法——两处都识别不到，整章于是从 `chapters/` 里消失
    # （`source_manifest.json.missing_chapters` 记着 221）。
    bare = INLINE_TAG_RE.sub("", probe).strip()
    if bare:
        probe = bare
    salvage = SALVAGE_HEADING_RE.match(probe)
    if salvage:
        return chinese_number(salvage.group(1)), salvage.group(2).strip(), ""
    match = CHAPTER_RE.search(probe)
    if not match:
        return None
    prefix = probe[: match.start()].strip()
    if prefix and prefix != "正文" and not VOLUME_PREFIX_RE.fullmatch(prefix):
        return None
    chapter_no = chinese_number(match.group(1))
    title = match.group(2).strip()
    # 「第220章我早有准备 第221章赞美」：一行里写了两个标题。标题里若还嵌着紧邻的
    # 下一个章号，就把它截掉——否则第220章会一直挂着第221章的名字（该章在正文里
    # 另有独立的标题行，由上面剥标签的那一步识别）。
    tail = CHAPTER_RE.search(title)
    if tail:
        try:
            following = chinese_number(tail.group(1))
        except (ValueError, KeyError):
            following = None
        if following == chapter_no + 1:
            title = title[: tail.start()].strip()
    return chapter_no, title, ("" if prefix == "正文" else prefix)


def decode_source(raw: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "big5"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise UnicodeError("Unable to decode source as UTF-8, GB18030, or Big5")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Source TXT file")
    parser.add_argument("--output-dir", required=True, type=Path, help="Run directory")
    parser.add_argument("--start", type=int, default=1, help="First chapter, inclusive (0 is allowed for a prologue)")
    parser.add_argument("--end", type=int, required=True, help="Last chapter, inclusive")
    parser.add_argument(
        "--front-matter",
        choices=("auto", "prologue", "skip"),
        default="auto",
        help=(
            "What to do with text before the first numbered heading. auto: include it as "
            "chapter 0 when it reads as prose, otherwise warn and drop it; prologue: always "
            "include it as chapter 0; skip: never include it (the pre-0.5 behaviour)"
        ),
    )
    parser.add_argument("--title", help="Novel title override")
    parser.add_argument("--force", action="store_true", help="Overwrite known generated files")
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    source = args.input.resolve()
    if not source.is_file():
        print(f"ERROR: source does not exist: {source}", file=sys.stderr)
        return 2
    if args.start < 0 or args.end < args.start:
        print("ERROR: require 0 <= start <= end", file=sys.stderr)
        return 2

    out = args.output_dir.resolve()
    if out.exists() and any(out.iterdir()) and not args.force:
        print(f"ERROR: output directory is not empty: {out} (use --force)", file=sys.stderr)
        return 2
    chapters_dir = out / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)

    raw = source.read_bytes()
    text, encoding = decode_source(raw)
    lines = text.splitlines(keepends=True)
    # In-place, so the source line numbering used by `source_line_start` and by
    # `resolve_evidence.py` still refers to the original file.
    cleaned_lines = [clean_inline_packaging(line) for line in lines]
    inline_packaging_lines = sum(1 for before, after in zip(lines, cleaned_lines) if before != after)
    lines = cleaned_lines
    records: dict[int, dict] = {}
    active: dict | None = None
    detected: list[int] = []
    # Everything before the first accepted numbered heading. Captured so it can be
    # reported (and optionally kept as chapter 0) instead of vanishing silently.
    front_matter_lines: list[str] | None = None
    toc_entries = 0
    # Line of the first heading past `--end`, where the scan stopped; None when the
    # requested range runs to the end of the file.
    scan_stop_line: int | None = None
    # Counted *before* the volume-prefix guard on purpose. When that guard rejects
    # every heading, `detected` is empty too, so it cannot be used to notice the
    # failure — but the heading-shaped lines are still there to be counted.
    heading_candidates = 0

    # ---- duplicate and garbled chapter numbers -------------------------------
    # A pirated TXT compilation corrupts a chapter four different ways, and merging
    # by number silently produces a wrong file for every one of them:
    #   * a block is pasted in twice (the 流氓老师 source carries 411-413 twice, the
    #     first copy inserted between chapters 384 and 386) — merging concatenates
    #     both copies into one chapter file;
    #   * the heading is repeated a few lines later with the number truncated and the
    #     body glued onto the same line (「第1516章 奇怪的东西」 then
    #     「第15章奇怪的东西老龙点点头说道…」) — merging cuts chapter 1516 in half;
    #   * the number is garbled (「第五百三一二章」, which parses as 502 because the
    #     last digit wins) — merging makes chapter 531 swallow chapter 532;
    #   * the 章 is lost and the heading survives only as 「正文 第1159 …」.
    # So classify every repeat before building anything, and report each decision.
    heading_lines: list[tuple[int, int, str]] = []
    for scan_no, scan_line in enumerate(lines, 1):
        scan_heading = match_heading(scan_line.rstrip("\r\n").strip().translate(FULLWIDTH_TRANS))
        if scan_heading is not None:
            heading_lines.append((scan_no, scan_heading[0], scan_heading[1]))

    def heading_block(index: int) -> str:
        """The chapter's text with blank lines and section markers removed.

        Section markers («正文 第386-405» / «正文 第414-417章») differ between two copies
        of the same pasted block, so comparing them raw makes an obvious duplicate look
        like a different chapter and sends it down the renumbering path.
        """
        start = heading_lines[index][0]
        end = heading_lines[index + 1][0] - 1 if index + 1 < len(heading_lines) else len(lines)
        return "".join(
            line for line in lines[start - 1:end]
            if line.strip() and not SALVAGE_RANGE_RE.match(line.strip().translate(FULLWIDTH_TRANS))
        )

    repeats: dict[int, list[int]] = {}
    for index, (_, number, _) in enumerate(heading_lines):
        repeats.setdefault(number, []).append(index)
    used_numbers = set(repeats)
    dropped_starts: set[int] = set()
    ignored_headings: set[int] = set()
    renumbered: dict[int, int] = {}
    duplicate_chapter_headings: list[dict] = []
    # Highest chapter number written *before* each heading, in file order. Recovery
    # from a mis-written number only makes sense forwards: if the candidate lands at
    # or below the highest number the file has already passed, the heading is a stray
    # re-paste of an earlier chapter, not a mis-numbered new one. Without this guard
    # the duplicate 「第397章」 pasted after 「第590章」 was renumbered to 414 — a number
    # the source deliberately skips (413 → 415) — and would have been emitted as
    # chapter 414 the moment a run asked for a range reaching that far, with 590's
    # text inside it.
    prefix_max: list[int] = []
    running_max = 0
    for _, scan_number, _ in heading_lines:
        prefix_max.append(running_max)
        running_max = max(running_max, scan_number)

    for number, indices in repeats.items():
        if len(indices) < 2:
            continue
        first_index = indices[0]
        for other_index in indices[1:]:
            line_no = heading_lines[other_index][0]
            previous = heading_lines[other_index - 1] if other_index else None
            gap = line_no - previous[0] if previous else 10 ** 9
            entry = {
                "chapter": number,
                "kept_at_line": heading_lines[first_index][0],
                "repeat_at_line": line_no,
                "title": heading_lines[other_index][2],
            }
            if heading_block(other_index) == heading_block(first_index):
                dropped_starts.add(line_no)
                entry["action"] = "丢弃重复块：与首次出现逐字相同"
            elif gap <= MANGLED_HEADING_GAP:
                ignored_headings.add(line_no)
                entry["action"] = "不作为标题：紧随前一标题的残缺重复，文本留在所属章节内"
            else:
                # A chapter whose number was written wrong. Recover it from position
                # rather than from the numeral, which is what is broken.
                candidate = (previous[1] + 1) if previous else number
                while candidate in used_numbers and candidate <= (previous[1] + 50 if previous else number):
                    candidate += 1
                following = heading_lines[other_index + 1] if other_index + 1 < len(heading_lines) else None
                if (
                    previous
                    and candidate not in used_numbers
                    and candidate > prefix_max[other_index]
                    and (following is None or candidate < following[1])
                ):
                    renumbered[line_no] = candidate
                    used_numbers.add(candidate)
                    entry["action"] = f"数字写坏，按位置重编号为第{candidate}章"
                    entry["renumbered_to"] = candidate
                else:
                    dropped_starts.add(line_no)
                    if previous and candidate <= prefix_max[other_index]:
                        entry["action"] = (
                            f"重复块且重编号目标（第{candidate}章）不高于文件已推进到的最大章号"
                            f"（第{prefix_max[other_index]}章）：判定为前文误贴的重复块，丢弃"
                        )
                    else:
                        entry["action"] = (
                            "重复块且编号无法从位置恢复：丢弃该块并记录行号，需人工复核"
                        )
            duplicate_chapter_headings.append(entry)

    for line_no, line in enumerate(lines, 1):
        stripped = line.rstrip("\r\n").strip()
        probe = stripped.translate(FULLWIDTH_TRANS)
        raw_match = CHAPTER_RE.search(probe) if len(probe) <= 120 else None
        if raw_match and TOC_TAIL_RE.search(probe):
            # "第一章 陨落的天才 ........ 1" is a table-of-contents entry, not a
            # heading: a real heading never ends in dot leaders and a page number.
            toc_entries += 1
        elif raw_match:
            heading_candidates += 1
        heading = match_heading(probe)
        if heading is None or line_no in ignored_headings:
            # Not a heading, or a mangled repeat of the heading just above: either
            # way the line is body text of whatever chapter is active.
            if active is not None:
                active["lines"].append(line)
            continue
        if line_no in dropped_starts:
            if active is not None:
                active["source_line_end"] = line_no - 1
            active = None
            continue
        chapter_no, title, prefix = heading
        chapter_no = renumbered.get(line_no, chapter_no)
        if front_matter_lines is None:
            front_matter_lines = lines[: line_no - 1]
        detected.append(chapter_no)
        if active is not None:
            active["source_line_end"] = line_no - 1
        if chapter_no > args.end and records:
            # First heading past the requested end. Everything below is out of scope,
            # including any renumbering decided from file position alone — so record
            # where the scan stopped and mark those decisions as not applied.
            scan_stop_line = line_no
            active = None
            break
        if args.start <= chapter_no <= args.end:
            record = records.get(chapter_no)
            if record is None:
                record = {
                    "chapter": chapter_no,
                    "title": PART_SUFFIX_RE.sub("", title).strip() or f"第{chapter_no}章",
                    "section_titles": [],
                    "volume": prefix or None,
                    "source_line_start": line_no,
                    "source_line_end": line_no,
                    "lines": [],
                }
                records[chapter_no] = record
            elif prefix and not record.get("volume"):
                record["volume"] = prefix
            if title and title not in record["section_titles"]:
                record["section_titles"].append(title)
            active = record
        else:
            active = None
        if active is not None:
            active["lines"].append(line)

    if active is not None:
        active["source_line_end"] = len(lines)

    # Report the duplicate-heading decisions. Only the ones inside the requested range
    # can affect this run; the rest are counted, so a reader can tell a clean book from
    # one whose duplicates merely happen to lie past `--end`. A renumbering decided
    # from file position is only applied if the scan actually reaches that line, so
    # say so instead of reporting a chapter number that will never exist.
    for entry in duplicate_chapter_headings:
        if "renumbered_to" in entry:
            entry["effective"] = entry["repeat_at_line"] in renumbered and (
                scan_stop_line is None or entry["repeat_at_line"] < scan_stop_line
            )
    duplicates_in_range = [
        entry for entry in duplicate_chapter_headings if entry["chapter"] <= args.end
    ]
    for entry in duplicates_in_range:
        print(
            f"WARNING: 第{entry['chapter']}章重复标题（行{entry['kept_at_line']} 与 "
            f"行{entry['repeat_at_line']}）：{entry['action']}",
            file=sys.stderr,
        )
        if "renumbered_to" in entry and not entry["effective"]:
            print(
                f"WARNING: 上条重编号（→第{entry['renumbered_to']}章）落在第 {args.end} 章之后，"
                f"本次范围外未生效；日后扩大范围时需重新判定",
                file=sys.stderr,
            )
    duplicates_out_of_range = len(duplicate_chapter_headings) - len(duplicates_in_range)
    if duplicates_out_of_range:
        print(
            f"NOTE: 另有 {duplicates_out_of_range} 处重复标题位于第 {args.end} 章之后，"
            f"本次范围外，未逐条告警（明细见 source_manifest.json 的 duplicate_chapter_headings）",
            file=sys.stderr,
        )

    # Text before the first numbered heading is either a prologue that belongs in the
    # graph or a title page / table of contents that does not. Report the decision
    # either way: dropping it silently is how the prologue of the run that prompted
    # this was lost — it appeared in no list, so nothing flagged its absence.
    front_matter: dict = {
        "mode": args.front_matter,
        "included": False,
        "char_count": 0,
        "reason": "首个编号标题之前没有正文",
    }
    head_lines = front_matter_lines or []
    head_text = "".join(head_lines).strip()
    if head_text:
        front_matter["block_char_count"] = len(head_text)
        kept_lines, leading_dropped, trailing_dropped = trim_front_matter(head_lines)
        kept_text = "".join(kept_lines).strip()
        front_matter["char_count"] = len(kept_text)
        # Shape alone is not enough: a title page plus 内容简介 plus a blurb reads
        # as long prose lines and passes looks_like_prose, but it is packaging.
        # Judge the *trimmed* block: trim_front_matter has already removed whatever
        # packaging precedes the prologue heading, so a marker that survives the
        # trim means the block really is packaging rather than story. Testing the
        # untrimmed block instead vetoes a clean prologue that merely sat behind an
        # ebook's title page — which is what it did to the run that prompted this,
        # dropping a 2,900-character prologue because the blurb six lines above it
        # mentioned 内容简介.
        block_packaging = [marker for marker in PACKAGING_MARKERS if marker in head_text]
        packaging = [marker for marker in PACKAGING_MARKERS if marker in kept_text]
        if block_packaging:
            front_matter["block_packaging_markers"] = block_packaging
        if packaging:
            front_matter["packaging_markers"] = packaging
        include = args.front_matter == "prologue" or (
            args.front_matter == "auto"
            and not packaging
            and looks_like_prose(kept_text)
        )
        if include:
            front_matter["leading_lines_dropped"] = leading_dropped
            front_matter["trailing_lines_dropped"] = trailing_dropped
            records[0] = {
                "chapter": 0,
                "title": front_matter_title(kept_lines),
                "section_titles": [],
                "volume": None,
                "source_line_start": leading_dropped + 1,
                "source_line_end": len(head_lines) - trailing_dropped,
                "lines": kept_lines,
            }
            front_matter["included"] = True
            front_matter["reason"] = (
                "按 --front-matter prologue 纳入第 0 章"
                if args.front_matter == "prologue"
                else "判定为序章正文，纳入第 0 章"
            )
            dropped = leading_dropped + trailing_dropped
            print(
                f"NOTE: 首个标题前 {len(kept_text)} 字按序章落为第 0 章"
                f"（标题：{records[0]['title']}，源文件第 {records[0]['source_line_start']}"
                f"–{records[0]['source_line_end']} 行"
                + (f"，已剥离 {dropped} 行电子书包装" if dropped else "")
                + "）",
                file=sys.stderr,
            )
        else:
            if args.front_matter == "skip":
                front_matter["reason"] = "按 --front-matter skip 跳过"
            elif packaging:
                front_matter["reason"] = (
                    f"含电子书包装／简介标记（{'、'.join(packaging)}），未纳入"
                )
            else:
                front_matter["reason"] = "判定为封面/目录类前置内容，未纳入"
            hint = "" if args.front_matter == "skip" else "；若确为序章请加 --front-matter prologue"
            print(
                f"WARNING: 首个标题前有 {len(kept_text)} 字正文未纳入图谱"
                f"（{front_matter['reason']}）{hint}",
                file=sys.stderr,
            )
    if toc_entries:
        print(
            f"WARNING: 忽略 {toc_entries} 行疑似目录条目（以点线加页码结尾）；"
            f"若正文章节因此缺失，请先清理源文件开头的目录页",
            file=sys.stderr,
        )

    # A number the source never writes as a heading is a gap in the source, not a
    # failure of this script. Both used to land in one `missing_chapters` list, which
    # made a faithful split of a file that skips 414/464/499 look like three
    # extraction failures — and a real extraction failure is the thing that needs
    # attention, so it must not be diluted by numbers that were never in the book.
    missing = [n for n in range(args.start, args.end + 1) if n not in records]
    missing_source_gaps = [n for n in missing if n not in used_numbers]
    missing_unresolved = [n for n in missing if n in used_numbers]
    for chapter_no in missing_unresolved:
        print(
            f"WARNING: 第{chapter_no}章在源文件中存在标题，却没有生成章节文件；"
            f"多半被误判为重复块或残缺标题，需人工复核",
            file=sys.stderr,
        )
    if missing_source_gaps:
        preview = "、".join(str(n) for n in missing_source_gaps[:12])
        print(
            f"NOTE: 源文件本身跳过 {len(missing_source_gaps)} 个章号（{preview}"
            f"{'…' if len(missing_source_gaps) > 12 else ''}）：相邻标题直接跳号，"
            f"不是切分失败",
            file=sys.stderr,
        )
    manifest_records = []
    for chapter_no in sorted(records):
        record = records[chapter_no]
        chapter_text = "".join(record.pop("lines"))
        chapter_path = chapters_dir / f"{chapter_no:03d}.txt"
        chapter_path.write_text(chapter_text, encoding="utf-8", newline="")
        record["text_path"] = str(chapter_path)
        record["char_count"] = len(chapter_text)
        record["sha256"] = hashlib.sha256(chapter_text.encode("utf-8")).hexdigest()
        manifest_records.append(record)

    # `--force` means "regenerate this directory", so a chapter file left over from
    # an earlier prepare must not survive: a stale `000.txt` with no record in
    # `chapters.jsonl` is invisible to validation but sits in the directory an
    # extraction pass globs, and the next pass can quote a chapter that no longer
    # exists.
    if args.force:
        written = {chapters_dir / f"{chapter_no:03d}.txt" for chapter_no in records}
        for stale in sorted(chapters_dir.glob("*.txt")):
            if stale not in written and stale.stem.isdigit():
                stale.unlink()
                print(f"NOTE: --force 清理过期章节文件 {stale.name}", file=sys.stderr)

    # Self-check. A prepare that silently produces one chapter is worse than one
    # that fails loudly: everything downstream then works perfectly on a fraction
    # of the book, and validation reports `valid: true`. The run that prompted
    # this check prepared 3,339 characters out of a 13 MB source because the book
    # opens chapters with 第一卷 and the prefix regex only knew 第X集.
    prepared_characters = sum(r["char_count"] for r in manifest_records)
    self_check: list[str] = []
    if heading_candidates >= 5 and len(manifest_records) <= 1:
        self_check.append(
            f"源文件有 {heading_candidates} 行章节标题形态，却只识别出 {len(manifest_records)} 章；"
            f"多半是卷前缀写法不在 VOLUME_PREFIX_RE 内（当前正则：{VOLUME_PREFIX_RE.pattern}）"
        )
    if manifest_records:
        # Compare against the source lines the records actually claim, not against
        # the whole file — a five-chapter request out of a 500-chapter book is not
        # a defect, and a whole-file comparison would call it one.
        span_start = min(r["source_line_start"] for r in manifest_records)
        span_end = max(r["source_line_end"] for r in manifest_records)
        span_characters = sum(len(line) for line in lines[span_start - 1:span_end])
        if span_characters and prepared_characters < span_characters * 0.5:
            self_check.append(
                f"prepared_characters={prepared_characters} 不足其覆盖行区间 "
                f"（第 {span_start}–{span_end} 行，{span_characters} 字）的 50%；"
                f"章节边界可能被漏识别"
            )
    for message in self_check:
        print(f"WARNING: 自检未通过 — {message}", file=sys.stderr)

    out.mkdir(parents=True, exist_ok=True)
    with (out / "chapters.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for record in manifest_records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    manifest = {
        "title": args.title or source.stem,
        "source_file": str(source),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_bytes": len(raw),
        "source_encoding": encoding,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "chapter_start": 0 if front_matter["included"] else args.start,
        "chapter_end": args.end,
        "front_matter": front_matter,
        "prepared_chapters": [r["chapter"] for r in manifest_records],
        "missing_chapters": missing,
        "missing_chapters_source_gap": missing_source_gaps,
        "missing_chapters_unresolved": missing_unresolved,
        "detected_heading_count": len(detected),
        "heading_shaped_lines": heading_candidates,
        "inline_packaging_lines_stripped": inline_packaging_lines,
        "duplicate_chapter_headings": duplicate_chapter_headings,
        "prepared_characters": prepared_characters,
        "self_check": self_check,
        "chapter_index": str(out / "chapters.jsonl"),
    }
    (out / "source_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    # Only a number the source actually writes but this script failed to produce is a
    # failure. A number the source never writes is a fact about the book.
    return 1 if (missing_unresolved or self_check) else 0


if __name__ == "__main__":
    raise SystemExit(main())
