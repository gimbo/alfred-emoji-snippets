#!/usr/bin/env python

"""gimbo.py - convert upstream *.alfredsnippets to gimbo versions.

This takes the emoji Alfred snipepts from
https://github.com/ericwbailey/alfred-emoji-snippets and munges them in various
ways I find desirable:

- Gather them all into one big snippets collection
  - Prefix each name with "Emoji | <Collection Name> | " to aid searching, etc.
- Remove hard-coded prefix/suffix from keywords, instead do it via info.plist
- Remove or rename some particular ones, particularly where there are name clashes.
- Add a better icon (taken with gratitude from the Joel Califa emoji pack
  promoted by Alfred docs).

"""

import json
import re
import shutil
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Snippet:
    collection: str
    snippet: str
    uid: str
    name: str
    keyword: str

    @classmethod
    def from_json(cls, json_text: str, collection: str):
        item = json.loads(json_text)['alfredsnippet']
        return cls(
            collection=collection,
            snippet=item['snippet'],
            uid=item['uid'],
            name=item['name'],
            keyword=item['keyword'],
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                "alfredsnippet" : {
                    "snippet" : self.snippet,
                    "uid" : self.uid,
                    "name" : self.name,
                    "keyword" : self.keyword,
                  }
            },
            ensure_ascii=False,
            indent=2,
        )


HERE = Path.cwd()
WORKSPACE = HERE / 'workspace'
FINAL_COLLECTION_NAME = "Gimbo Big Emoji Collection.alfredsnippets"
COLLECTION_IGNORES = (
    # Ignore this as it seems like a placeholder or something
    '^Arrows.alfredsnippets$',
    # Ignore this as it's the final product!
    f'^{FINAL_COLLECTION_NAME}$',
)
COMMON_PREFIX = ':'
COMMON_SUFFIX = ':'
ICON_PATH = 'gimbo_icon.png'

SNIPPET_ACTIONS = {

    # Removals

    # person-in-lotus-position-boat ; duplicated in People
    ('[Emoji] Activity.alfredsnippets', 'DB104057-67D9-464E-87A7-E5C6A5C9E83F'): 'remove',
    # person-rowing-boat ; duplicated within this collection
    ('[Emoji] Activity.alfredsnippets', '2CB14D66-8A2C-490E-B5BC-497C719BDE0D'): 'remove',
    # person-in-suit-levitating ; duplicated in People
    ('[Emoji] Activity.alfredsnippets', '73D962B3-0883-46DB-BF17-7886E0E0D6BE'): 'remove',

    # meditating ; duplicated within this collection
    ('[Emoji] Aliases.alfredsnippets', '1EFA2E1A-FC94-4E9E-8CA6-CCD9881F8EDB'): 'remove',
    # movie-camera ; prefer version in Devices
    ('[Emoji] Aliases.alfredsnippets', '382C5551-7790-438B-B0DD-7D5085AE7562'): 'remove',
    # razor ; prefer version in Objects
    ('[Emoji] Aliases.alfredsnippets', 'F5246F75-8B74-4A1C-A546-EA13B904CB80'): 'remove',

    # chestnut ; duplicated in Plants
    ('[Emoji] Food and Drink.alfredsnippets', '21C550E1-8B7C-4C41-91FB-6A8FB11805DB'): 'remove',
    # mushroom ; duplicated in Plants
    ('[Emoji] Food and Drink.alfredsnippets', 'A7D1C140-433A-4CB5-9D08-0E039673A514'): 'remove',

    # umbrella ; prefer version in Weather
    ('[Emoji] Objects.alfredsnippets', 'E5539CBF-8C94-4E63-A76F-28F5BB9A778D'): 'remove',

    # potable-water ; duplicated in Objects
    ('[Emoji] Symbols.alfredsnippets', 'E7A892D4-EC10-4CEB-8FA4-DF406E69C24A'): 'remove',
    # white-flower ; duplicated in Plants
    ('[Emoji] Symbols.alfredsnippets', '746F2037-7C6A-4C6D-95B7-3E202A2EFD2B'): 'remove',

    # shooting-star ; duplicated in Weather
    ('[Emoji] Travel and Places.alfredsnippets', 'E7AFDB70-D184-4550-9DAF-AFC7F17AA1E2'): 'remove',

    # Renamings; usually name clases with different icons where we want to keep both

    # Was video-game
    ('[Emoji] Aliases.alfredsnippets', '7BBB3467-E963-4563-A24F-5ADB2A7134E3'): 'rename:space-invader:Space Invader',
    # Was no-good
    ('[Emoji] Aliases.alfredsnippets', '4E959109-F9A1-471A-BE3E-E9F2FB91B923'): 'rename:ng:No Good (block)',
    # Was shooting-star
    ('[Emoji] Weather.alfredsnippets', '17D5AB5B-7EE4-44AF-BDC6-52A1B0330DF7'): 'rename:shoting-star-block:Shooting Star (block)'
    
}

# Warning: global state (which gets modified) here!
SNIPPETS_BY_KEYWORD: defaultdict[str, list[Snippet]] = defaultdict(list)
SNIPPETS_BY_NAME: defaultdict[str, list[Snippet]] = defaultdict(list)


def main():
    if WORKSPACE.exists():
        print('Wiping workspace\n')
        shutil.rmtree(WORKSPACE)
    WORKSPACE.mkdir()
    for snippetfile in HERE.glob('*.alfredsnippets'):
        if should_be_ignored(snippetfile):
            continue
        tweak_snippetfile(snippetfile)
        print()
    collect_and_compress_to_new_single_snippetfile()
    print()
    report_on_clashes()


def should_be_ignored(snippetfile: Path) -> bool:
    for pattern in COLLECTION_IGNORES:
        if re.match(pattern, snippetfile.name):
            return True
    return False


def tweak_snippetfile(snippetfile):
    print(f'Processing {snippetfile.name}')
    print(f'  Extracting to folder {snippetfile.name}')
    new_dir_path = WORKSPACE / snippetfile.name
    extract_and_process_snippets(snippetfile, new_dir_path)
    print(f'  Compressing to folder {snippetfile.name}.alfredsnippets')


def extract_and_process_snippets(snippetfile: Path, dest: Path):
    with zipfile.ZipFile(snippetfile) as snipzip:
        dest.mkdir()
        snipzip.extractall(path=dest)
        snippet_paths = list(dest.glob('*.json'))
        print(f'  {len(snippet_paths)} JSON snippets extracted; tweaking keywords')
        for snippet_path in snippet_paths:
            process_snippet(snippet_path)


def process_snippet(snippet_path: Path):
    snippet = Snippet.from_json(
        snippet_path.read_text(),
        collection=snippet_path.parent.name,
    )
    tweaked_snippet = tweak_snippet(snippet)
    if tweaked_snippet is None:
        # Dropped it
        snippet_path.unlink()
        return
    snippet_path.write_text(
        tweaked_snippet.to_json()
    )


def tweak_snippet(snippet: Snippet):
    """Remove/rename if desired; remember we've seen it; prefix name for searching"""
    snippet.keyword = re.sub(r'^:(.+):$', r'\1', snippet.keyword)
    action = SNIPPET_ACTIONS.get((snippet.collection, snippet.uid))
    if action is not None:
        if action == 'remove':
            return None
        elif action.startswith('rename:'):
            snippet.keyword, snippet.name = action[7:].split(':')
    SNIPPETS_BY_KEYWORD[snippet.keyword].append(snippet)
    SNIPPETS_BY_NAME[snippet.name].append(snippet)
    collection = snippet.collection.replace('[Emoji] ', '').replace('.alfredsnippets', '')
    snippet.name = f'Emoji | {collection} | {snippet.name} | {snippet.keyword}'
    return snippet


def collect_and_compress_to_new_single_snippetfile():
    """Make big final zip!"""
    print('Gathering snippets up')
    collections = list(WORKSPACE.iterdir())
    final = WORKSPACE / FINAL_COLLECTION_NAME
    final.mkdir()
    for collection in collections:
        print(f'  {collection}')
        snippets = collection.glob('*.json')
        for snippet in snippets:
            destination = WORKSPACE / final / snippet.name
            if destination.exists():
                raise ValueError(snippet)
            snippet.rename(destination)
    shutil.copyfile(ICON_PATH, final / 'icon.png')
    (collections[0] / 'info.plist').rename(final / 'info.plist')
    tweak_info_plist(
        final / 'info.plist',
        prefix=COMMON_PREFIX,
        suffix=COMMON_SUFFIX,
    )
    with zipfile.ZipFile(final.name, mode='w') as snippets_zip:
        for path in final.iterdir():
            snippets_zip.write(path, arcname=path.name)


def tweak_info_plist(info_plist_path: Path, prefix: str, suffix: str):
    """Add desired common prefix/suffix into info.plist"""
    info_plist_path.write_text(
        re.sub(
            (
                r'(^\s+<key>snippetkeywordprefix</key>\n'
                r'\s+<string>)(</string>\n'
                r'\s+<key>snippetkeywordsuffix</key>\n'
                r'\s+<string>)(</string>)'
            ),
            r'\1' + prefix + r'\2' + suffix + r'\3',
            info_plist_path.read_text(),
            flags=re.MULTILINE,
        )
    )


def report_on_clashes():
    report_on_keyword_clashes()
    print()
    report_on_name_clashes()

def report_on_keyword_clashes():
    keyword_clashes = {
        keyword: snippets
        for keyword, snippets in SNIPPETS_BY_KEYWORD.items()
        if len(snippets) > 1
    }
    if not keyword_clashes:
        print('No keyword clashes')
    else:
        print('Keyword clashes:')
        for keyword, clashes in keyword_clashes.items():
            print(f'  {keyword}')
            for snippet in clashes:
                print(f'    {snippet.snippet} \t {snippet.uid} \t\t {snippet.collection} \t\t {snippet.name}')


def report_on_name_clashes():
    name_clashes = {
        name: snippets
        for name, snippets in SNIPPETS_BY_NAME.items()
        if len(snippets) > 1
    }
    if not name_clashes:
        print('No name clashes')
    else:
        print('Name clashes:')
        for name, clashes in name_clashes.items():
            print(f'  {name}')
            for snippet in clashes:
                print(f'    {snippet.snippet} \t {snippet.uid} \t\t {snippet.collection} \t\t {snippet.keyword}')


if __name__ == "__main__":
    main()