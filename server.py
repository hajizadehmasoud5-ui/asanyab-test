import os
import subprocess
import sys
from pathlib import Path

try:
    from flask import Flask, jsonify
except ModuleNotFoundError:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'Flask>=3.0,<4'])
    from flask import Flask, jsonify

from alanoffer_blueprint import create_alanoffer_blueprint
from drlinq_marketplace import create_drlinq_marketplace_blueprint

ROOT = Path(__file__).resolve().parent
# Cloudiva persistent path. Can still be overridden explicitly with DATA_ROOT.
DATA_ROOT = Path(os.environ.get('DATA_ROOT', '/data'))
DATA_ROOT.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.register_blueprint(create_alanoffer_blueprint(DATA_ROOT))
app.register_blueprint(create_drlinq_marketplace_blueprint(DATA_ROOT))

@app.get('/')
def root():
    return jsonify(ok=True, service='drlinq-demand-matching', version='0.5.0')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '3000')))
