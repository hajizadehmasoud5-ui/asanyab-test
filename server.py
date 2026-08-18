from myapp import app, DATA_ROOT
from alanoffer_chat import create_alanoffer_chat_blueprint

app.register_blueprint(create_alanoffer_chat_blueprint(DATA_ROOT))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)
