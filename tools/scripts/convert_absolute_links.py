import re
import os
from pathlib import Path

# Project root is two levels up from this script (tools/scripts/convert_absolute_links.py)
project_root = Path(__file__).resolve().parents[2]
print(f"[Link Converter] Project root: {project_root}")

# Pattern to find file:/// links pointing to SHIM project
# Matches: file:///[any_drive_or_path]/SHIM/[target_path]#[anchor]
link_pattern = re.compile(r'file:///[^)\s]*?/SHIM/([^)#\s]+)(#[^)\s]+)?', re.IGNORECASE)

def convert_file(file_path: Path):
    content = file_path.read_text(encoding='utf-8')
    modified = False
    
    def replacer(match):
        nonlocal modified
        rel_target = match.group(1).replace('\\', '/')
        anchor = match.group(2) or ""
        
        # Target path relative to the project root
        target_path_from_root = project_root / rel_target
        
        # Calculate relative path from this file's folder to target
        try:
            rel_path = os.path.relpath(target_path_from_root, file_path.parent)
            rel_path = rel_path.replace('\\', '/')
            modified = True
            return rel_path + anchor
        except Exception as e:
            print(f"Error resolving relative path for {rel_target} in {file_path}: {e}")
            return match.group(0)

    new_content = link_pattern.sub(replacer, content)
    if modified:
        file_path.write_text(new_content, encoding='utf-8')
        print(f"[Link Converter] Converted: {file_path.relative_to(project_root)}")

def main():
    for md_file in project_root.rglob('*.md'):
        # Skip directories (such as design.md/)
        if not md_file.is_file():
            continue
        # Skip virtual environments and node_modules
        if any(part.startswith('.') or part == 'node_modules' for part in md_file.parts):
            continue
        convert_file(md_file)

if __name__ == '__main__':
    main()
