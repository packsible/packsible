from flask import Flask, request, jsonify

app = Flask(__name__)


class InvalidUsage(Exception):
    status_code = 400

    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['message'] = self.message
        return rv


@app.route('/build')
def build():
    if request.method == 'POST':
        if 'file' not in request.files:
            raise InvalidUsage()


@app.errorhandler(InvalidUsage)
def handle_invalid_usage(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response


def run_server(config):
    app.config['UPLOAD_FOLDER'] = config.get('server_upload_folder', '/tmp')

    app.run(port='9988')
