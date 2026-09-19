"""Load the shared project catalogue without granting execution permissions."""
import json
import os
from pathlib import Path, PureWindowsPath, PurePosixPath


class RegistryError(ValueError):
    pass


FIELDS = ('key', 'name', 'win_path', 'description', 'linux_path', 'repo_url')


def default_registry_path(module_file, platform=None, environ=None):
    environ = os.environ if environ is None else environ
    override = environ.get('GAVRIK_PROJECTS_FILE')
    if override:
        return Path(override)
    if (os.name if platform is None else platform) == 'nt':
        return Path('C:/Users/HP/gavrik/support/project-sync/projects.json')
    return Path(module_file).resolve().parent / 'support/project-sync/projects.json'


def _identity(key, win_path):
    if key == 'gavrik' and PureWindowsPath(win_path).name.casefold() == 'gavrik-pc':
        return 'gavrik-pc'
    return key


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RegistryError('Duplicate JSON property: ' + key)
        result[key] = value
    return result


def load_shared_projects(existing, project_type, module_file, registry_path=None):
    path = Path(registry_path) if registry_path is not None else default_registry_path(module_file)
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=_pairs)
    except (OSError, ValueError) as exc:
        raise RegistryError(f'Cannot load shared project registry {path}: {exc}') from exc
    if not isinstance(data, dict) or data.get('schema_version') != 1 or not isinstance(data.get('projects'), list):
        raise RegistryError('Expected schema_version=1 and projects list')
    rows = {}
    for row in data['projects']:
        if not isinstance(row, dict) or set(row) != set(FIELDS):
            raise RegistryError('Project fields must exactly match ' + ', '.join(FIELDS))
        for field in FIELDS[:4]:
            if not isinstance(row[field], str) or not row[field].strip():
                raise RegistryError('Empty or invalid field: ' + field)
        for field in FIELDS[4:]:
            if row[field] is not None and (not isinstance(row[field], str) or not row[field].strip()):
                raise RegistryError('Invalid optional field: ' + field)
        if not PureWindowsPath(row['win_path']).is_absolute():
            raise RegistryError('Windows project path must be absolute: ' + row['key'])
        if row['linux_path'] is not None and not PurePosixPath(row['linux_path']).is_absolute():
            raise RegistryError('Linux project path must be absolute: ' + row['key'])
        if row['key'] in rows:
            raise RegistryError('Duplicate project key: ' + row['key'])
        rows[row['key']] = row
    local_keys = set()
    for local in existing:
        key = _identity(local.key, local.win_path)
        if key in local_keys:
            raise RegistryError('Duplicate local project key: ' + key)
        local_keys.add(key)
        if key not in rows:
            raise RegistryError('Shared registry would lose local project: ' + key)
        row = rows[key]
        if PureWindowsPath(local.win_path) != PureWindowsPath(row['win_path']):
            raise RegistryError('Conflicting Windows path: ' + key)
        for field in ('repo_url', 'linux_path'):
            old = getattr(local, field)
            # The PC copy previously reused the server identity; keep /root/gavrik
            # exclusively on the actual server catalogue entry.
            if key == 'gavrik-pc' and field == 'linux_path' and old == '/root/gavrik':
                old = None
            if old is not None and old != row[field]:
                raise RegistryError('Conflicting ' + field + ': ' + key)
    return [project_type(**row) for row in rows.values()]
