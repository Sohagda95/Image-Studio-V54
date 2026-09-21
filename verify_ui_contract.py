"""Dependency-free static UI contract checks for the Windows build."""
from pathlib import Path
import ast, sys

APP = Path(__file__).with_name('app.py')
REQUIRED = {
    'BatchProductionTab': [
        'apply_selected_preset', 'pick_source', 'pick_output', 'add_job',
        'remove_job', 'move', 'clear_jobs', 'start', 'toggle_pause',
        'stop', 'reset', 'done', 'failed', 'was_cancelled',
        'refresh_history', 'report'
    ]
}

def main():
    tree = ast.parse(APP.read_text(encoding='utf-8'), filename=str(APP))
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
    errors=[]
    for cls, names in REQUIRED.items():
        node=classes.get(cls)
        if node is None:
            errors.append(f'Missing class: {cls}')
            continue
        methods={n.name for n in node.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
        for name in names:
            if name not in methods:
                errors.append(f'{cls}: missing method {name}')
    if errors:
        print('UI contract test: FAIL')
        print('\n'.join(errors))
        return 1
    print('UI contract test: PASS')
    return 0

if __name__ == '__main__':
    sys.exit(main())
