#!/usr/bin/env python3
"""Build the complete, self-authored GenericDataset without network access."""

from __future__ import annotations

import ast
import hashlib
import json
import random
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SEED = 20261031
VERSIONS = {"Minimal": 60, "Balanced": 300, "Big": 1200}
LANGUAGES = ["Python", "C++", "C", "Assembly", "HTML", "CSS", "JS", "RUST", "PHP", "TYPESCRIPT"]
LICENSE = "CC0-1.0"


def pick(items: list[str], index: int, stride: int) -> str:
    return items[(index * stride + index // 7) % len(items)]


def record_id(collection: str, index: int) -> str:
    digest = hashlib.sha256(f"GenericDataset:{collection}:{index}".encode()).hexdigest()[:16]
    return f"{collection.lower()}-{index:05d}-{digest}"


NAMES = ["Ari", "Bea", "Cato", "Dina", "Eli", "Fara", "Gio", "Hana", "Ivo", "Juno", "Kian", "Luma", "Mara", "Nico", "Oren", "Pia"]
PLACES = ["harbor workshop", "hill library", "night garden", "glasshouse", "clock tower", "riverside market", "map room", "old observatory", "forest station", "community kitchen", "sunlit attic", "canal bridge"]
OBJECTS = ["brass compass", "paper kite", "quiet radio", "painted key", "seed box", "folding lantern", "pocket telescope", "blue notebook", "wind chime", "wooden ruler", "tiny bell", "rain gauge"]
GOALS = ["find a missing route", "repair a small mistake", "share a useful discovery", "prepare for a neighbor", "solve a patient puzzle", "make a difficult choice", "learn a new skill", "protect a fragile plan"]
LESSONS = ["careful listening made the next step visible", "small trials were better than dramatic guesses", "asking for help gave the idea room to grow", "a clear note saved everyone time", "patience turned a problem into a practice", "kindness made the work lighter", "the answer arrived after the question became specific", "sharing credit improved the result"]


def story(index: int) -> dict:
    lead = pick(NAMES, index, 3)
    friend = pick(NAMES, index + 5, 5)
    place = pick(PLACES, index, 7)
    obj = pick(OBJECTS, index, 11)
    goal = pick(GOALS, index, 13)
    lesson = pick(LESSONS, index, 17)
    title = f"{lead} and the {obj.title()}"
    text = (
        f"{lead} arrived at the {place} before the morning crowd. A {obj} rested beside a hand-drawn sign, "
        f"and the sign asked anyone nearby to {goal}. {lead} did not pretend to know the answer. Instead, "
        f"they wrote down what was certain, what was missing, and one safe first step.\n\n"
        f"Soon {friend} joined them with a practical question: what would change if they tried the smallest version first? "
        f"Together they tested one idea, noticed a detail they had overlooked, and adjusted their plan. The {obj} was not magical; "
        f"it was useful because it encouraged them to observe carefully. By afternoon, their work gave the people at the {place} "
        f"a simple way forward.\n\n"
        f"Before leaving, {lead} placed the sign back where it belonged and added a final sentence for the next visitor: {lesson}. "
        f"{friend} smiled, because the day had ended with a solution and a method for finding the next one."
    )
    return {"id": record_id("stories", index), "title": title, "text": text, "genre": "gentle_problem_solving", "themes": ["curiosity", "cooperation", "care"], "reading_level": "general", "word_count": len(text.split()), "license": LICENSE}


TOPICS = [
    ("planning a study session", "choose one topic, make a short schedule, and reserve time to review"),
    ("organizing a small project", "name the outcome, divide it into visible steps, and check progress after each step"),
    ("understanding a new concept", "start with a plain definition, test it with an example, and explain it in your own words"),
    ("recovering from a mistake", "describe what happened, fix the smallest harmful part, and record what to do next time"),
    ("writing a friendly message", "open warmly, state the purpose directly, and end with a clear next action"),
    ("choosing between two options", "list the important constraints, compare them, and select the option that fits the goal"),
    ("debugging a simple issue", "reproduce the problem, isolate one variable, and test a focused fix"),
    ("building a daily habit", "make the first action small, attach it to a routine, and track it without judgment"),
]


def conversation(index: int) -> dict:
    topic, guidance = TOPICS[index % len(TOPICS)]
    name = pick(NAMES, index, 9)
    detail = pick(["twenty quiet minutes", "a visible checklist", "one example", "a notebook page", "a timer", "a trusted friend"], index, 5)
    return {
        "id": record_id("conversations", index),
        "topic": topic,
        "skills": ["clarification", "structured_help", "encouragement"],
        "messages": [
            {"role": "user", "content": f"Hi, I am {name}. I need help with {topic}. Where should I begin?"},
            {"role": "assistant", "content": f"Hello, {name}. A good beginning is to make the goal concrete. For {topic}, {guidance}. Start with {detail} so the plan stays manageable."},
            {"role": "user", "content": "That sounds doable. How can I tell whether the first step is working?"},
            {"role": "assistant", "content": "Choose one observable signal before you begin. After the first step, ask whether you produced the planned result and whether the next step is clearer. If not, reduce the scope and try again; that is progress, not failure."},
            {"role": "user", "content": "Thanks. I will try the small version first."},
            {"role": "assistant", "content": "You are welcome. Keep a short note about what helped, then use that note to make the next attempt easier."},
        ],
        "license": LICENSE,
    }


def information(index: int) -> dict:
    mode = index % 5
    if mode == 0:
        a, b = index % 97 + 3, (index * 7) % 89 + 2
        answer = f"{a} + {b} = {a + b}. Addition combines quantities, so the result is the total of the two numbers."
        question, domain, keys = f"What is {a} plus {b}?", "arithmetic", ["addition", "numbers"]
    elif mode == 1:
        meters = index % 48 + 2
        answer = f"One meter equals 100 centimeters. Therefore {meters} meters equals {meters * 100} centimeters."
        question, domain, keys = f"How many centimeters are in {meters} meters?", "measurement", ["units", "conversion"]
    elif mode == 2:
        value = index % 41 + 5
        answer = f"To decide whether {value} is even, divide it by two and check the remainder. Its remainder is {value % 2}, so {value} is {'even' if value % 2 == 0 else 'odd'}."
        question, domain, keys = f"Is {value} even or odd, and why?", "logic", ["remainder", "parity"]
    elif mode == 3:
        answer = "A sorted list keeps items in an agreed order. Sorting helps because related values become easier to scan, compare, and search. A useful first check is whether each item is no larger than the item after it."
        question, domain, keys = "Why is sorting a list useful?", "computing", ["sorting", "lists"]
    else:
        answer = "A shadow forms when an object blocks some light. The side behind the object receives less light than the surrounding area, so it appears darker. The shape changes when the light or object moves."
        question, domain, keys = "Why does an object make a shadow?", "everyday_science", ["light", "shadow"]
    return {"id": record_id("info", index), "domain": domain, "difficulty": "introductory", "question": question, "answer": answer, "keywords": keys, "license": LICENSE}


def code_for(language: str, index: int) -> tuple[str, str, list[str]]:
    n = index % 37 + 3
    suffix = f"_{n}_{index // 37}"
    if language == "Python":
        return (f"Write a Python function that sums positive integers through {n}.", f"def sum_through{suffix}(limit: int = {n}) -> int:\n    if limit < 0:\n        raise ValueError('limit must be nonnegative')\n    return limit * (limit + 1) // 2\n", ["function", "arithmetic"])
    if language == "C++":
        return (f"Write a C++ function that clamps an integer into the range 0 through {n}.", f"#include <algorithm>\n\nint clamp{suffix}(int value) {{\n    return std::clamp(value, 0, {n});\n}}\n", ["function", "bounds"])
    if language == "C":
        return (f"Write a C function that returns the larger of a value and {n}.", f"int at_least{suffix}(int value) {{\n    return value < {n} ? {n} : value;\n}}\n", ["function", "conditional"])
    if language == "Assembly":
        return (f"Write an x86-64 NASM function that adds {n} to its first integer argument.", f"; NASM x86-64, System V calling convention\nglobal add{suffix}\nsection .text\nadd{suffix}:\n    mov rax, rdi\n    add rax, {n}\n    ret\n", ["nasm", "x86_64"])
    if language == "HTML":
        return (f"Write an accessible HTML card that displays task number {n}.", f"<!doctype html>\n<html lang=\"en\">\n  <body>\n    <main>\n      <article class=\"task-card\" aria-labelledby=\"task{suffix}\">\n        <h1 id=\"task{suffix}\">Task {n}</h1>\n        <p>Start with one clear, useful action.</p>\n      </article>\n    </main>\n  </body>\n</html>\n", ["markup", "accessibility"])
    if language == "CSS":
        return (f"Write CSS for a readable task card with spacing based on {n} pixels.", f".task-card{suffix} {{\n  max-width: 42rem;\n  margin: {n}px auto;\n  padding: {n}px;\n  border: 1px solid #4b5563;\n  border-radius: 0.5rem;\n  line-height: 1.5;\n}}\n", ["styles", "layout"])
    if language == "JS":
        return (f"Write a JavaScript function that keeps values at least {n}.", f"export function atLeast{suffix}(value) {{\n  if (!Number.isFinite(value)) throw new TypeError('value must be finite');\n  return Math.max(value, {n});\n}}\n", ["function", "validation"])
    if language == "RUST":
        return (f"Write a Rust function that adds {n} to each integer in a slice.", f"pub fn add_to_each{suffix}(values: &[i64]) -> Vec<i64> {{\n    values.iter().map(|value| value + {n}).collect()\n}}\n", ["function", "iterator"])
    if language == "PHP":
        return (f"Write a PHP function that clamps a number from 0 through {n}.", f"<?php\nfunction clamp{suffix}(int $value): int {{\n    return max(0, min({n}, $value));\n}}\n", ["function", "bounds"])
    if language == "TYPESCRIPT":
        return (f"Write a TypeScript function that returns true when a value is at least {n}.", f"export function isAtLeast{suffix}(value: number): boolean {{\n  if (!Number.isFinite(value)) throw new TypeError('value must be finite');\n  return value >= {n};\n}}\n", ["function", "types"])
    raise ValueError(language)


def coding(language: str, index: int, collection: str) -> dict:
    actual = LANGUAGES[index % len(LANGUAGES)] if language == "Mixed" else language
    prompt, code, tags = code_for(actual, index + (10000 if language == "Mixed" else 0))
    return {"id": record_id(collection, index), "language": actual, "prompt": prompt, "code": code, "tags": tags, "difficulty": "introductory", "license": LICENSE}


def write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def write_edition(directory: Path, records: list[dict], schema: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    total = len(records)
    train_end, validation_end = total * 8 // 10, total * 9 // 10
    splits = {"train": records[:train_end], "validation": records[train_end:validation_end], "test": records[validation_end:]}
    for name, values in splits.items():
        write_jsonl(directory / f"{name}.jsonl", values)
    (directory / "metadata.json").write_text(json.dumps({"format": "jsonl", "schema": schema, "records": total, "splits": {name: len(values) for name, values in splits.items()}, "license": LICENSE, "origin": "original_local_generation", "seed": SEED}, indent=2) + "\n", encoding="utf-8")


def validate(root: Path) -> dict[str, dict]:
    manifest: dict[str, dict] = {}
    seen_ids: set[str] = set()
    paths = []
    for directory in ("GenericStories", "GenericConversations", "GenericInfo", "GenericCoding"):
        paths.extend((root / directory).rglob("*.jsonl"))
    for path in sorted(paths):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        if not rows:
            raise ValueError(f"empty dataset file: {path}")
        for row in rows:
            if row["id"] in seen_ids:
                raise ValueError(f"duplicate id: {row['id']}")
            seen_ids.add(row["id"])
            if row.get("license") != LICENSE:
                raise ValueError(f"missing license: {row['id']}")
            blob = json.dumps(row, ensure_ascii=False).lower()
            if "todo" in blob or "placeholder" in blob:
                raise ValueError(f"placeholder content: {row['id']}")
            if row.get("language") == "Python":
                ast.parse(row["code"])
        rel = path.relative_to(root.parent).as_posix()
        manifest[rel] = {"records": len(rows), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return manifest


def main() -> None:
    random.seed(SEED)
    for collection in ("GenericStories", "GenericConversations", "GenericInfo", "GenericCoding"):
        target = ROOT / collection
        if target.exists():
            shutil.rmtree(target)
    for edition_index, (version, count) in enumerate(VERSIONS.items()):
        offset = edition_index * 10000
        write_edition(ROOT / "GenericStories" / version, [story(offset + i) for i in range(count)], "story.v1")
        write_edition(ROOT / "GenericConversations" / version, [conversation(offset + i) for i in range(count)], "conversation.v1")
        write_edition(ROOT / "GenericInfo" / version, [information(offset + i) for i in range(count)], "information.v1")
    for language in ["Mixed", *LANGUAGES]:
        count = 400 if language == "Mixed" else 200
        write_edition(ROOT / "GenericCoding" / language, [coding(language, i, f"coding-{language.lower()}") for i in range(count)], "coding.v1")
    manifest = {"name": "GenericDataset", "version": "1.0.0", "origin": "original_local_generation", "license": LICENSE, "files": validate(ROOT)}
    (ROOT / "GenericDataset" / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {sum(item['records'] for item in manifest['files'].values())} records across {len(manifest['files'])} JSONL files")


if __name__ == "__main__":
    main()
