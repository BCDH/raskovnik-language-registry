#!/usr/bin/env python3
"""Choose registry release versions without rewriting unrelated TEI source."""

from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = Path('registry/registry.xml')
POM = Path('pom.xml')
VERSION_CHANGE = re.compile(r'(?m)^(?P<indent>[ \t]*)<change type="registryVersion" n="(?P<version>[^"]+)" when="(?P<when>[^"]+)">(?P<text>[^<]*)</change>$')
PACKAGE_VERSION = re.compile(r'(<project(?=[\s>])[^>]*>[\s\S]*?<version>)(\d+)\.(\d+)\.(\d+)(</version>)', re.MULTILINE)


def previous(path):
    result = subprocess.run(['git', 'show', 'HEAD:'+str(path)], cwd=ROOT, capture_output=True)
    if result.returncode:
        raise ValueError('Cannot read committed '+str(path))
    return result.stdout.decode('utf-8')


def one_match(pattern, source, label):
    matches = list(pattern.finditer(source))
    if len(matches) != 1:
        raise ValueError('Expected one '+label)
    return matches[0]


def prepare(registry, pom, old_registry, old_pom, now):
    current = one_match(VERSION_CHANGE, registry, 'registryVersion change')
    committed = one_match(VERSION_CHANGE, old_registry, 'committed registryVersion change')
    package = one_match(PACKAGE_VERSION, pom, 'package version')
    old_package = one_match(PACKAGE_VERSION, old_pom, 'committed package version')
    current_package = tuple(map(int, package.group(2, 3, 4)))
    committed_package = tuple(map(int, old_package.group(2, 3, 4)))
    current_version = current.group('version')
    committed_version = committed.group('version')
    if (current_version != committed_version) != (current_package != committed_package):
        raise ValueError('Registry and package versions must advance together')
    if current_version != committed_version:
        return registry, pom, current_version, '.'.join(map(str, current_package)), False
    if registry == old_registry:
        raise ValueError('No registry source changes to prepare for release')
    return advance(registry, pom, now)


def advance(registry, pom, now):
    current = one_match(VERSION_CHANGE, registry, 'registryVersion change')
    package = one_match(PACKAGE_VERSION, pom, 'package version')
    current_package = tuple(map(int, package.group(2, 3, 4)))
    current_version = current.group('version')
    if not re.fullmatch(r'\d{4}\.\d{1,2}\.\d{1,2}-\d+', current_version):
        raise ValueError('Unsupported registry version: '+current_version)
    belgrade_now = now.astimezone(ZoneInfo('Europe/Belgrade'))
    date = f'{belgrade_now.year}.{belgrade_now.month}.{belgrade_now.day}'
    old_date, old_sequence = current_version.rsplit('-', 1)
    if tuple(map(int, old_date.split('.'))) > tuple(map(int, date.split('.'))):
        raise ValueError('Registry version is dated after today')
    next_version = date+'-'+str(int(old_sequence)+1 if old_date == date else 1)
    next_package = '.'.join(map(str, (*current_package[:2], current_package[2]+1)))
    timestamp = now.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    new_change = (f'{current.group("indent")}<change type="registryVersion" n="{next_version}" when="{timestamp}">'
                  'Registry release.</change>\n'
                  f'{current.group("indent")}<change n="{current_version}" when="{current.group("when")}">{current.group("text")}</change>')
    registry = registry[:current.start()]+new_change+registry[current.end():]
    pom = pom[:package.start()]+package.group(1)+next_package+package.group(5)+pom[package.end():]
    return registry, pom, next_version, next_package, True


def ensure_local(registry, pom, state, now):
    current = one_match(VERSION_CHANGE, registry, 'registryVersion change').group('version')
    match = one_match(PACKAGE_VERSION, pom, 'package version')
    package = '.'.join(match.group(2, 3, 4))
    content_hash = hashlib.sha256(registry.encode()).hexdigest()
    if state['installed']:
        installed_package = state['package_version']
        if not re.fullmatch(r'\d+\.\d+\.\d+', installed_package):
            raise ValueError('Installed package version is invalid')
        if tuple(map(int, package.split('.'))) < tuple(map(int, installed_package.split('.'))):
            raise ValueError('Local registry downgrade requires the explicit release-set workflow')
        if package == installed_package:
            if current == state['registry_version'] and content_hash == state['content_sha256']:
                return registry, pom, current, package, False
            if re.fullmatch(r'\d{4}\.\d{1,2}\.\d{1,2}-\d+', state['registry_version']):
                def parts(version):
                    return tuple(map(int, version.replace('-', '.').split('.')))
                if parts(current) < parts(state['registry_version']):
                    raise ValueError('Local registry downgrade requires the explicit release-set workflow')
            return advance(registry, pom, now)
        if current == state['registry_version']:
            raise ValueError('Package version advanced without registry version')
        return registry, pom, current, package, False
    tag = 'v'+package
    result = subprocess.run(['git', 'show', tag+':'+str(REGISTRY)], cwd=ROOT, capture_output=True)
    if result.returncode:
        # A newly prepared version may have no tag yet. Its explicit TEI revision
        # is kept for the first local install.
        return registry, pom, current, package, False
    tagged = result.stdout.decode('utf-8')
    tagged_version = one_match(VERSION_CHANGE, tagged, 'tagged registryVersion change').group('version')
    if current == tagged_version and registry != tagged:
        return advance(registry, pom, now)
    return registry, pom, current, package, False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installed-state', type=Path)
    args = parser.parse_args()
    try:
        registry = (ROOT/REGISTRY).read_text()
        pom = (ROOT/POM).read_text()
        if args.installed_state:
            updated_registry, updated_pom, registry_version, package_version, changed = ensure_local(
                registry, pom, json.loads(args.installed_state.read_text()), datetime.now(timezone.utc))
        else:
            updated_registry, updated_pom, registry_version, package_version, changed = prepare(
                registry, pom, previous(REGISTRY), previous(POM), datetime.now(timezone.utc))
        if changed:
            (ROOT/REGISTRY).write_text(updated_registry)
            (ROOT/POM).write_text(updated_pom)
        print(f'Registry {registry_version}; package {package_version}' + (' (already prepared)' if not changed else ''))
    except (OSError, ValueError) as error:
        print('Release preparation failed: '+str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
