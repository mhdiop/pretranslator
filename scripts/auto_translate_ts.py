import os
import json
import re
import requests
import subprocess
from lxml import etree

DEEPL_API_KEY = os.environ["DEEPL_API_KEY"]
DEEPL_URL = "https://api-free.deepl.com/v2/translate"

CACHE_FILE = "scripts/translation_cache.json"

PLACEHOLDER_PATTERN = r"%\d+|%L\d+|%n"


def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf8") as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def protect_placeholders(text):

    placeholders = re.findall(PLACEHOLDER_PATTERN, text)

    mapping = {}

    protected = text

    for i, ph in enumerate(placeholders):

        token = f"__PH_{i}__"

        protected = protected.replace(ph, token)

        mapping[token] = ph

    return protected, mapping


def restore_placeholders(text, mapping):

    restored = text

    for token, ph in mapping.items():
        restored = restored.replace(token, ph)

    return restored


def batch_translate(texts, target_lang):

    headers = {
        "Authorization": f"DeepL-Auth-Key {DEEPL_API_KEY}"
    }

    payload = {
        "auth_key": DEEPL_API_KEY,
        "target_lang": target_lang,
    }

    for t in texts:
        payload.setdefault("text", []).append(t)

    r = requests.post(DEEPL_URL, data=payload, headers=headers)

    r.raise_for_status()

    return [t["text"] for t in r.json()["translations"]]


def get_modified_ts_files():

    cmd = ["git", "diff", "--name-only", "HEAD^", "HEAD"]

    result = subprocess.run(cmd, capture_output=True, text=True)

    files = result.stdout.splitlines()

    return [f for f in files if f.endswith(".ts")]


def process_file(path, cache):

    parser = etree.XMLParser(remove_blank_text=False)

    tree = etree.parse(path, parser)

    root = tree.getroot()

    lang = root.attrib.get("language", "EN").upper()

    print("Processing:", path, "→", lang)

    messages = []
    texts = []
    mappings = []
    file_changed = False

    for message in root.findall(".//message"):

        source = message.find("source")
        translation = message.find("translation")

        if translation is None:
            continue

        if translation.get("type") != "unfinished":
            continue

        source_text = source.text.strip()

        key = f"{source_text}:{lang}"

        if key in cache:

            translation.text = cache[key]
            translation.attrib.pop("type", None)

            file_changed = True

            print(source_text, "→", cache[key], "(cached)")

            continue

        protected, mapping = protect_placeholders(source_text)

        messages.append((message, source_text))
        texts.append(protected)
        mappings.append(mapping)

    if texts:

        translated_batch = batch_translate(texts, lang)

        for (message, source_text), translated, mapping in zip(messages, translated_batch, mappings):

            restored = restore_placeholders(translated, mapping)

            translation = message.find("translation")

            translation.text = restored
            translation.attrib.pop("type", None)

            cache[f"{source_text}:{lang}"] = restored

            file_changed = True

            print(source_text, "→", restored)

    if not file_changed:
        return False

    tree.write(
        path,
        encoding="utf-8",
        xml_declaration=True,
        pretty_print=True
    )

    return True


def main():

    cache = load_cache()

    files = get_modified_ts_files()

    modified = False

    for f in files:

        if process_file(f, cache):
            modified = True

    save_cache(cache)

    if modified:
        print("Translations updated")
    else:
        print("No translations needed")


if __name__ == "__main__":
    main()
