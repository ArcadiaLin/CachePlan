#!/usr/bin/env python3
"""从 references/refs.bib 生成论文用的 refs.bib，剥掉仓库内部字段。

为什么需要这一步：本仓库约定每个 bib 条目带一条 note，写明它支撑哪个 open
question / decision / experiment（见 references/README.md）。那是项目元数据，
用中文写，且不属于文献信息。而 ACM-Reference-Format.bst 会把 note 原样排进
参考文献表，于是 pdflatex 遇到中文字符直接 fatal error。

所以这里按字段名剥离，而不是按语言过滤 —— 就算 note 改成英文，它也不该出现在
投出去的论文里。只依赖标准库，不引入任何第三方包。
"""

import sys

DROP = {"note"}


def strip(text: str) -> str:
    out, i, n = [], 0, len(text)
    while i < n:
        # 只在条目内部的字段起始位置判断；条目外的内容（注释、@string）原样保留。
        if text[i] == "=" and out:
            # 回看等号左边的字段名。
            j = len(out) - 1
            while j >= 0 and out[j] in " \t\n":
                j -= 1
            k = j
            while k >= 0 and (out[k].isalnum() or out[k] in "_-"):
                k -= 1
            name = "".join(out[k + 1 : j + 1]).lower()
            if name in DROP:
                # 跳过整个字段：等号之后的值（可能是 {…}、"…" 或裸 token），
                # 以及紧随其后的那个逗号。
                i += 1
                while i < n and text[i] in " \t\n":
                    i += 1
                if i < n and text[i] == "{":
                    depth = 0
                    while i < n:
                        if text[i] == "{":
                            depth += 1
                        elif text[i] == "}":
                            depth -= 1
                            if depth == 0:
                                i += 1
                                break
                        i += 1
                elif i < n and text[i] == '"':
                    i += 1
                    while i < n and text[i] != '"':
                        i += 1
                    i += 1
                else:
                    while i < n and text[i] not in ",}":
                        i += 1
                while i < n and text[i] in " \t":
                    i += 1
                if i < n and text[i] == ",":
                    i += 1
                # 连字段名一起从输出里删掉。
                del out[k + 1 :]
                continue
        out.append(text[i])
        i += 1
    return "".join(out)


def main() -> int:
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, encoding="utf-8") as f:
        text = f.read()
    result = strip(text)
    banner = (
        "% 本文件由 tools/strip-notes.py 从 ../references/refs.bib 生成，请勿手改。\n"
        "% 唯一的文献元数据来源是 references/refs.bib；这里只是剥掉了 note 字段的副本。\n\n"
    )
    with open(dst, "w", encoding="utf-8") as f:
        f.write(banner + result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
