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
from drlinq_secretary import create_drlinq_secretary_blueprint
from drlinq_assistant import create_drlinq_assistant_blueprint
from drlinq_referral import create_drlinq_referral_blueprint
from drlinq_referral_short import create_drlinq_referral_short_blueprint
from request_guard import install_request_guard
try:
    from drlinq_push import create_drlinq_push_blueprint
except ModuleNotFoundError:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'pywebpush>=2.0,<3', 'cryptography>=42,<47'])
    from drlinq_push import create_drlinq_push_blueprint

ROOT = Path(__file__).resolve().parent
DATA_ROOT = Path(os.environ.get('DATA_ROOT', '/data'))
DATA_ROOT.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
install_request_guard(app)
app.register_blueprint(create_alanoffer_blueprint(DATA_ROOT))
app.register_blueprint(create_drlinq_marketplace_blueprint(DATA_ROOT))
app.register_blueprint(create_drlinq_secretary_blueprint(DATA_ROOT))
app.register_blueprint(create_drlinq_assistant_blueprint(DATA_ROOT))
app.register_blueprint(create_drlinq_referral_blueprint(DATA_ROOT))
app.register_blueprint(create_drlinq_referral_short_blueprint(DATA_ROOT))
app.register_blueprint(create_drlinq_push_blueprint(DATA_ROOT))

@app.get('/')
def root():
    return jsonify(ok=True, service='drlinq-platform', version='0.8.3-security')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '3000')))
