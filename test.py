from flask import Flask
app = Flask(__name__)

@app.route('/')
def home():
    return "OK"

if __name__ == '__main__':
    app.run(debug=False, threaded=False, port=5000)