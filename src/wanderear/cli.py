"""WanderEar command line interface."""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

from . import __version__, audio
from .config import settings
from .store import LocalStore


def _warn(message: str) -> None:
    print(f"! {message}", file=sys.stderr)


def _run(buffer, args, store: LocalStore) -> int:
    from . import pipeline

    location = (
        {"lat": args.lat, "lon": args.lon}
        if getattr(args, "lat", None) is not None
        else None
    )
    card = pipeline.analyze(
        buffer,
        classifier=args.classifier,
        narrator=args.narrator,
        top_n=args.top_n,
        location=location,
        store=store,
        spectrogram=not args.no_spectrogram,
        warn=_warn,
    )

    print(card.postcard["title"])
    print("-" * len(card.postcard["title"]))
    print(card.postcard["body"])
    print()
    labels = card.labels
    print("sounds: " + ", ".join(f"{lab['name']} {lab['confidence']:.2f}" for lab in labels))
    print(f"postcard: {card.id}  ({card.classifier} + {card.postcard['narrator']})")
    return 0


def cmd_listen(args) -> int:
    print(f"recording ~{args.seconds:g}s … (make some noise, or make none)")
    buffer = audio.record(args.seconds)
    return _run(buffer, args, LocalStore())


def cmd_analyze(args) -> int:
    buffer = audio.load(args.path)
    return _run(buffer, args, LocalStore())


def cmd_list(args) -> int:
    cards = LocalStore().all()
    if not cards:
        print("no postcards yet — try: wanderear listen --seconds 8")
        return 0
    for c in cards:
        top = c["labels"][0]["name"] if c.get("labels") else "?"
        print(f"{c['id']}  {c['context'].get('season',''):<7}"
              f"{c['context'].get('local_time',''):<9}{top:<16}{c['postcard']['title']}")
    return 0


def cmd_show(args) -> int:
    item = LocalStore().get(args.id)
    if not item:
        print(f"no postcard with id {args.id}", file=sys.stderr)
        return 1
    print(json.dumps(item, indent=2))
    return 0


def cmd_gallery(args) -> int:
    store = LocalStore()
    items = store.all()
    cards = []
    for item in reversed(items):
        labels = ", ".join(f"{lab['name']} {lab['confidence']:.2f}" for lab in item["labels"])
        img = ""
        if item.get("spectrogram_path"):
            try:
                rel = Path(item["spectrogram_path"]).relative_to(store.home)
                img = f'<img src="{html.escape(str(rel))}" alt="spectrogram">'
            except ValueError:
                pass
        cards.append(
            "<article>"
            f"<h2>{html.escape(item['postcard']['title'])}</h2>"
            f"<p>{html.escape(item['postcard']['body'])}</p>"
            f"<p class='meta'>{html.escape(labels)} · "
            f"{html.escape(item['context'].get('local_time',''))} "
            f"{html.escape(item['context'].get('season',''))} · "
            f"{html.escape(item['classifier'])}</p>{img}</article>"
        )
    doc = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>WanderEar postcards</title><style>"
        "body{font-family:system-ui;max-width:760px;margin:2rem auto;padding:0 1rem;"
        "background:#0e1512;color:#e8f0ea}"
        "article{border:1px solid #2a3a33;border-radius:12px;padding:1rem 1.2rem;"
        "margin:1rem 0;background:#121a16}"
        ".meta{color:#8fae9c;font-size:.85rem}"
        "img{width:100%;border-radius:8px;margin-top:.5rem}</style></head><body>"
        "<h1>&#127811; WanderEar postcards</h1>"
        f"<p>{len(cards)} moment(s) outside.</p>{''.join(cards)}</body></html>"
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc)
    print(f"wrote {out} ({len(items)} postcards)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wanderear", description="Shazam for the wild.")
    p.add_argument("--version", action="version", version=f"wanderear {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    listen = sub.add_parser("listen", help="record live audio and make a postcard")
    listen.add_argument("--seconds", type=float, default=8.0)
    _add_common(listen)
    listen.set_defaults(func=cmd_listen)

    analyze = sub.add_parser("analyze", help="classify an existing audio file")
    analyze.add_argument("path")
    _add_common(analyze)
    analyze.set_defaults(func=cmd_analyze)

    listing = sub.add_parser("list", help="list saved postcards")
    listing.set_defaults(func=cmd_list)

    show = sub.add_parser("show", help="print a postcard as JSON")
    show.add_argument("id")
    show.set_defaults(func=cmd_show)

    gallery = sub.add_parser("gallery", help="build an HTML gallery of your postcards")
    gallery.add_argument("--out", default=str(settings.home / "gallery.html"))
    gallery.set_defaults(func=cmd_gallery)

    search = sub.add_parser("search", help="find saved postcards similar to a sound")
    search.add_argument("--like", metavar="ID", default=None, help="similar to a saved postcard")
    search.add_argument("--file", metavar="PATH", default=None, help="similar to an audio file")
    search.add_argument("--limit", type=int, default=5)
    search.set_defaults(func=cmd_search)

    doctor = sub.add_parser("doctor", help="check what is installed and working")
    doctor.set_defaults(func=cmd_doctor)

    watch = sub.add_parser("watch", help="keep listening on an interval and log postcards")
    watch.add_argument("--seconds", type=float, default=8.0)
    watch.add_argument("--interval", type=float, default=60.0)
    watch.add_argument("--count", type=int, default=0, help="0 = until interrupted")
    _add_common(watch)
    watch.set_defaults(func=cmd_watch)

    sync = sub.add_parser("sync", help="upload postcards to the hosted gallery")
    sync.add_argument("url", help="base URL of the gallery, e.g. https://x.onrender.com")
    sync.set_defaults(func=cmd_sync)

    return p


def cmd_search(args) -> int:
    from . import embeddings
    from .classify import Label

    store = LocalStore()
    if bool(args.like) == bool(args.file):
        print("provide exactly one of --like <id> or --file <path>", file=sys.stderr)
        return 2

    if args.like:
        item = store.get(args.like)
        if not item:
            print(f"no postcard with id {args.like}", file=sys.stderr)
            return 1
        query = item.get("embedding")
        if not query:
            query = embeddings.label_vector(
                [Label(lab["name"], lab["confidence"]) for lab in item.get("labels", [])]
            )
    else:
        buffer = audio.load(args.file)
        from .pipeline import classifier_for

        labels = classifier_for("passthrough").classify(buffer, top_n=args.limit)
        query = embeddings.embed(buffer, labels)

    results = store.search(query, limit=args.limit)
    if not results:
        print("no saved postcards yet")
        return 0
    for item, score in results:
        print(f"{score:0.3f}  {item['id']}  {item['postcard']['title']}")
    return 0


def cmd_doctor(args) -> int:
    import shutil

    checks: list[tuple[str, bool, str]] = []

    checks.append(("python>=3.10", sys.version_info >= (3, 10), sys.version.split()[0]))
    for mod in ("numpy", "sounddevice", "matplotlib"):
        try:
            __import__(mod)
            checks.append((mod, True, "installed"))
        except ImportError:
            checks.append((mod, False, "not installed"))
    ffmpeg_path = shutil.which("ffmpeg")
    checks.append(("ffmpeg", ffmpeg_path is not None, ffmpeg_path or "missing"))

    from .narrate import GemmaNarrator

    narrator = GemmaNarrator()
    models = narrator.installed_models()
    checks.append(("ollama server", bool(models) or _server_up(narrator), narrator.url))
    if narrator.use_installed_gemma():
        checks.append(("gemma model", True, narrator.model))
    else:
        checks.append(("gemma model", False, "none pulled (ollama pull gemma3:4b)"))

    yamnet_ok = _yamnet_available()
    checks.append(("yamnet model", yamnet_ok, "found" if yamnet_ok else "not installed"))

    store = LocalStore()
    store.ensure()
    checks.append(("data dir", True, str(store.home)))
    checks.append(("postcards", True, str(len(store.all()))))

    print("WanderEar doctor\n")
    for name, ok, detail in checks:
        print(f"  [{'ok' if ok else '--'}] {name:<16} {detail}")
    return 0


def _server_up(narrator) -> bool:
    try:
        with __import__("urllib.request", fromlist=["urlopen"]).urlopen(
            f"{narrator.url}/api/tags", timeout=2
        ):
            return True
    except Exception:
        return False


def _yamnet_available() -> bool:
    try:
        from .classify import get_classifier

        get_classifier("yamnet")
        return True
    except Exception:
        return False


def cmd_watch(args) -> int:
    store = LocalStore()
    count = 0
    print(f"listening every {args.interval:g}s (Ctrl-C to stop)")
    while args.count == 0 or count < args.count:
        try:
            buffer = audio.record(args.seconds)
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        _run(buffer, args, store)
        count += 1
        if args.count == 0 or count < args.count:
            import time

            time.sleep(args.interval)
    return 0


def cmd_sync(args) -> int:
    from .sync import sync

    try:
        result = sync(LocalStore(), args.url)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"uploaded {result['uploaded']} postcard(s), {result['media']} media file(s) "
          f"to {args.url} ({result['already']} already there)")
    return 0


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--classifier",
        default="auto",
        choices=["auto", "passthrough", "yamnet", "panns", "clap"],
    )
    p.add_argument("--narrator", default="auto", choices=["auto", "template", "gemma"])
    p.add_argument("--top-n", type=int, default=settings.top_k)
    p.add_argument("--no-spectrogram", action="store_true")
    p.add_argument("--lat", type=float, default=None)
    p.add_argument("--lon", type=float, default=None)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())