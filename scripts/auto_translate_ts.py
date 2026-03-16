import os
import json
import requests
import subprocess
from lxml import etree

DEEPL_API_KEY = os.environ["DEEPL_API_KEY"]
DEEPL_URL = "https://api-free.deepl.com/v2/translate"

CACHE_FILE = "scripts/translation_cache.json"


def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf8") as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def translate(text, target_lang):

    headers = {
        "Authorization": f"DeepL-Auth-Key {DEEPL_API_KEY}"
    }

    payload = {
        "text": text,
        "target_lang": target_lang
    }

    r = requests.post(DEEPL_URL, data=payload, headers=headers)
    r.raise_for_status()

    return r.json()["translations"][0]["text"]


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

    changed = False

    for message in root.findall(".//message"):

        source = message.find("source")
        translation = message.find("translation")

        if translation is None:
            continue

        if translation.get("type") != "unfinished":
            continue

        source_text = source.text.strip()

        if source_text in cache:
            translated = cache[source_text]

        else:

            translated = translate(source_text, lang)

            cache[source_text] = translated

        translation.text = translated
        translation.attrib.pop("type", None)

        print(f"{source_text} -> {translated}")

        changed = True

    if changed:

        tree.write(
            path,
            encoding="utf-8",
            xml_declaration=True,
            pretty_print=True
        )

    return changed


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


if __name__ == "__main__":
    main()
