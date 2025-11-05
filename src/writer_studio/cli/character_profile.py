import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict

import yaml

from writer_studio.logging import get_logger, init_logging
from writer_studio.persistence.db import (
    get_character_profile,
    get_character_profile_by_id,
    get_character_template_by_id,
    init_db,
    list_character_profiles,
    list_character_templates,
    save_character_profile,
    save_character_template,
    search_character_profiles,
    update_character_profile,
)

log = get_logger("character_profile.cli")


def _load_template(answer_language: str) -> Dict[str, Any]:
    base_dir_env = os.getenv("CHAR_TASKS_DIR")
    if base_dir_env:
        base_dir = Path(base_dir_env)
    else:
        base_dir = Path(__file__).resolve().parents[3] / "tasks" / "character_profile"

    candidate = base_dir / f"{answer_language}.yaml"
    if not candidate.exists():
        log.warning(
            "Character template for lang=%s not found at %s; falling back to en.yaml",
            answer_language,
            candidate,
        )
        candidate = base_dir / "en.yaml"
    with candidate.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("task", {}).get("template", {})


def _ask_scalar(prompt: str, default: str | None = None) -> str:
    while True:
        if default is not None:
            val = input(f"{prompt} [default: {default}]: ").strip()
            if not val:
                return default
            return val
        val = input(f"{prompt}: ").strip()
        if val:
            return val
        print("Please enter a non-empty value.")


def _ask_list(
    prompt: str, min_items: int = 0, default: list[str] | None = None
) -> list[str]:
    items: list[str] = []
    if default:
        print(
            f"Enter items for {prompt} (blank to stop, Enter to keep current).\n"
            f"Current: {', '.join(default)}"
        )
    else:
        print(f"Enter items for {prompt} (blank line to stop)")
    first = True
    while True:
        val = input("- ").strip()
        if not val:
            if first and default is not None and len(default) >= min_items:
                return default
            if len(items) >= min_items:
                break
            print(f"Please add at least {min_items} item(s).")
            continue
        items.append(val)
        first = False
    return items


def _walk_and_fill(
    obj: Dict[str, Any], defaults: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    defaults = defaults or {}
    for key, value in obj.items():
        current_default = defaults.get(key)
        if isinstance(value, dict):
            print(f"\n[{key}]")
            result[key] = _walk_and_fill(value, current_default or {})
        elif isinstance(value, list):
            # For list templates filled with "" entries
            min_items = max(1, len(value)) if value and isinstance(value[0], str) else 0
            if isinstance(current_default, list):
                result[key] = _ask_list(
                    key, min_items=min_items, default=current_default
                )
            else:
                result[key] = _ask_list(key, min_items=min_items)
        else:
            if isinstance(current_default, str):
                result[key] = _ask_scalar(key, default=current_default)
            else:
                result[key] = _ask_scalar(key)
    return result


def _fill_sections(
    template_root: Dict[str, Any],
    defaults: Dict[str, Any] | None,
    sections_to_edit: list[str],
) -> Dict[str, Any]:
    """Fill only specific top-level sections; keep others from defaults."""
    defaults = defaults or {}
    result: Dict[str, Any] = {}
    for key, value in template_root.items():
        if key in sections_to_edit:
            if isinstance(value, dict):
                print(f"\n[{key}] (editing)")
                result[key] = _walk_and_fill(value, defaults.get(key) or {})
            elif isinstance(value, list):
                min_items = (
                    max(1, len(value)) if value and isinstance(value[0], str) else 0
                )
                if isinstance(defaults.get(key), list):
                    result[key] = _ask_list(
                        key, min_items=min_items, default=defaults.get(key)
                    )
                else:
                    result[key] = _ask_list(key, min_items=min_items)
            else:
                d = defaults.get(key) if isinstance(defaults.get(key), str) else None
                result[key] = _ask_scalar(key, default=d)
        else:
            result[key] = defaults.get(key, value)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Character profile CLI: collect, save to SQLite, and "
            "retrieve for cross-checks."
        )
    )
    sub = parser.add_subparsers(dest="command")

    collect = sub.add_parser(
        "collect", help="Interactive collection and optional persistence"
    )
    collect.add_argument(
        "--language",
        default=os.getenv("CHAR_LANG", "zh-CN"),
        help="Template language (e.g., en, zh-CN)",
    )
    collect.add_argument(
        "--update",
        action="store_true",
        help="Edit an existing profile by --id and re-save",
    )
    collect.add_argument(
        "--id",
        type=int,
        default=None,
        help="Profile id to update when --update is set",
    )
    collect.add_argument(
        "--json-out",
        default=None,
        help="Optional path to write the filled profile as JSON",
    )
    collect.add_argument(
        "--yaml-out",
        default=None,
        help="Optional path to write the filled profile as YAML",
    )
    collect.add_argument(
        "--persist",
        action="store_true",
        default=True,
        help="Persist the collected profile into SQLite (default: true)",
    )

    show = sub.add_parser("show", help="Show a saved profile by name and language")
    show.add_argument("--language", required=True, help="Language code of the profile")
    show.add_argument("--name", required=True, help="Character name to retrieve")

    ls = sub.add_parser("list", help="List saved profiles (optionally by language)")
    ls.add_argument("--language", default=None, help="Filter by language")

    # Templates management
    tcollect = sub.add_parser("tcollect", help="Collect and save a template")
    tcollect.add_argument(
        "--language",
        default=os.getenv("CHAR_LANG", "zh-CN"),
        help="Template language (e.g., en, zh-CN)",
    )
    tcollect.add_argument(
        "--source", default=None, help="Origin (history/novel/person)"
    )
    tcollect.add_argument(
        "--json-out", default=None, help="Optional path to write JSON"
    )
    tcollect.add_argument(
        "--yaml-out", default=None, help="Optional path to write YAML"
    )
    tcollect.add_argument(
        "--persist", action="store_true", default=True, help="Persist template"
    )

    tlist = sub.add_parser("tlist", help="List saved templates")
    tlist.add_argument("--language", default=None, help="Filter by language")

    tshow = sub.add_parser("tshow", help="Show a template by id")
    tshow.add_argument("--id", type=int, required=True, help="Template id")

    use_t = sub.add_parser("use_template", help="Create character from a template")
    use_t.add_argument("--id", type=int, required=True, help="Template id to use")
    use_t.add_argument(
        "--language", default=None, help="Override language (default: template lang)"
    )
    use_t.add_argument("--name", default=None, help="New character name")
    use_t.add_argument("--json-out", default=None, help="Optional path to write JSON")
    use_t.add_argument("--yaml-out", default=None, help="Optional path to write YAML")
    use_t.add_argument(
        "--persist", action="store_true", default=True, help="Persist new profile"
    )

    search = sub.add_parser("search", help="Search by name or JSON fields")
    search.add_argument("--language", default=None, help="Filter by language")
    search.add_argument(
        "--q",
        default=None,
        help="Free-text search in name and raw JSON",
    )
    search.add_argument(
        "--field",
        default=None,
        help="JSON field path (e.g., traits or background.details)",
    )
    search.add_argument(
        "--value",
        default=None,
        help="Partial value to match in the specified JSON field",
    )
    search.add_argument("--limit", type=int, default=50, help="Max results to show")

    args = parser.parse_args()

    init_logging(None)
    init_db()

    if args.command == "show":
        data = get_character_profile(args.language, args.name)
        if not data:
            print("Not found.")
            return
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    if args.command == "list":
        items = list_character_profiles(args.language, limit=100)
        for it in items:
            print(
                f"[{it['id']}] {it['lang']} :: {it['name']} "
                f"(updated {it['updated_at']})"
            )
        return

    if args.command == "tshow":
        t = get_character_template_by_id(args.id)
        if not t:
            print("Not found.")
            return
        print(json.dumps(t, ensure_ascii=False, indent=2))
        return

    if args.command == "tlist":
        items = list_character_templates(getattr(args, "language", None), limit=100)
        for it in items:
            print(
                f"[{it['id']}] {it['lang']} :: {it['name']} "
                f"source={it.get('source') or ''} (updated {it['updated_at']})"
            )
        return

    if args.command == "search":
        items = search_character_profiles(
            lang=args.language,
            name_like=None,
            q=getattr(args, "q", None),
            field=getattr(args, "field", None),
            value_like=getattr(args, "value", None),
            limit=getattr(args, "limit", 50),
        )
        if not items:
            print("No matches.")
            return
        for it in items:
            print(
                f"[{it['id']}] {it['lang']} :: {it['name']} "
                f"(updated {it['updated_at']})"
            )
        return

    if args.command == "use_template":
        t = get_character_template_by_id(int(args.id))
        if not t:
            raise SystemExit("Template id not found")
        template_lang = t.get("lang")
        language = (
            getattr(args, "language", None)
            or template_lang
            or os.getenv("CHAR_LANG", "zh-CN")
        )
        tmpl = _load_template(language)
        defaults = t.get("template") or {}
        print("\n=== Create Character From Template ===")
        default_new_name = getattr(args, "name", None) or t.get("name")
        new_name = _ask_scalar("name", default=default_new_name)
        filled = _fill_sections(
            tmpl["character_profile"],
            defaults,
            sections_to_edit=["backstory", "relationships"],
        )
        filled["name"] = new_name
        print("\n=== Completed Character Profile (JSON) ===")
        print(json.dumps({"character_profile": filled}, ensure_ascii=False, indent=2))
        if getattr(args, "json_out", None):
            Path(args.json_out).write_text(
                json.dumps({"character_profile": filled}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"Wrote JSON to: {args.json_out}")
        if getattr(args, "yaml_out", None):
            Path(args.yaml_out).write_text(
                yaml.safe_dump(
                    {"character_profile": filled}, allow_unicode=True, sort_keys=False
                ),
                encoding="utf-8",
            )
            print(f"Wrote YAML to: {args.yaml_out}")
        if getattr(args, "persist", True):
            row_id = save_character_profile(language, new_name, filled)
            print(f"Saved to SQLite: id={row_id} lang={language} name={new_name}")
        return

    # Default to collect if no subcommand provided
    # Default to collect if no subcommand provided (or explicit collect)
    language = getattr(args, "language", os.getenv("CHAR_LANG", "zh-CN"))
    # If updating by id, load existing profile as defaults
    defaults: Dict[str, Any] | None = None
    default_name: str | None = None
    default_lang: str | None = None
    if getattr(args, "update", False):
        if not getattr(args, "id", None):
            raise SystemExit("--update requires --id of the profile to edit")
        existing = get_character_profile_by_id(int(args.id))
        if not existing:
            raise SystemExit("Profile id not found")
        defaults = existing.get("profile") or {}
        default_name = existing.get("name")
        default_lang = existing.get("lang")
        language = default_lang or language
    tmpl = _load_template(language)
    if not tmpl or "character_profile" not in tmpl:
        raise SystemExit(
            "Template missing 'character_profile' root; please check "
            "tasks/character_profile/<lang>.yaml"
        )

    if args.command == "tcollect":
        print("\n=== Character Template Collection ===")
        t_filled = _walk_and_fill(tmpl["character_profile"], defaults)
        print("\n=== Completed Template (JSON) ===")
        print(json.dumps({"character_profile": t_filled}, ensure_ascii=False, indent=2))
        if getattr(args, "json_out", None):
            Path(args.json_out).write_text(
                json.dumps(
                    {"character_profile": t_filled}, ensure_ascii=False, indent=2
                ),
                encoding="utf-8",
            )
            print(f"Wrote JSON to: {args.json_out}")
        if getattr(args, "yaml_out", None):
            Path(args.yaml_out).write_text(
                yaml.safe_dump(
                    {"character_profile": t_filled}, allow_unicode=True, sort_keys=False
                ),
                encoding="utf-8",
            )
            print(f"Wrote YAML to: {args.yaml_out}")
        if getattr(args, "persist", True):
            t_name = (t_filled.get("name") or "").strip() or "(unnamed)"
            row_id = save_character_template(
                language, t_name, t_filled, getattr(args, "source", None)
            )
            print(f"Saved template: id={row_id} lang={language} name={t_name}")
        return

    print("\n=== Character Profile Collection ===")
    filled = _walk_and_fill(tmpl["character_profile"], defaults)

    print("\n=== Completed Character Profile (JSON) ===")
    print(json.dumps({"character_profile": filled}, ensure_ascii=False, indent=2))

    if getattr(args, "json_out", None):
        Path(args.json_out).write_text(
            json.dumps({"character_profile": filled}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Wrote JSON to: {args.json_out}")
    if getattr(args, "yaml_out", None):
        Path(args.yaml_out).write_text(
            yaml.safe_dump(
                {"character_profile": filled}, allow_unicode=True, sort_keys=False
            ),
            encoding="utf-8",
        )
        print(f"Wrote YAML to: {args.yaml_out}")

    if getattr(args, "persist", True):
        name = (filled.get("name") or "").strip()
        if not name:
            print("Warning: name is empty; saving under '(unnamed)'.")
            name = "(unnamed)"
        if getattr(args, "update", False) and getattr(args, "id", None):
            # If name/lang changed, update them; otherwise keep existing
            updated = update_character_profile(
                int(args.id),
                filled,
                name=name if name != (default_name or name) else None,
                lang=language if language != (default_lang or language) else None,
            )
            if updated:
                print(f"Updated SQLite: id={args.id} lang={language} name={name}")
            else:
                print("No update performed (row not found)")
        else:
            row_id = save_character_profile(language, name, filled)
            print(f"Saved to SQLite: id={row_id} lang={language} name={name}")


if __name__ == "__main__":
    main()