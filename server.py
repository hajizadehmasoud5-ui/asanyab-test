import os
from pathlib import Path

try:
    from myapp import app
except ModuleNotFoundError as exc:
    if exc.name != 'requests':
        raise
    from flask import Flask
    from alanoffer_blueprint import create_alanoffer_blueprint

    ROOT = Path(__file__).resolve().parent
    DATA_ROOT = Path(os.environ.get('DATA_ROOT', str(ROOT / 'data')))
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    app = Flask(__name__)
    app.register_blueprint(create_alanoffer_blueprint(DATA_ROOT))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '3000')))
