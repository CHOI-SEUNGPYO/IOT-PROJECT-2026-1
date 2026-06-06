from flask import Flask, render_template

app = Flask(__name__)

# ==========================================
# 1. 페이지 라우팅 (각 버튼을 눌렀을 때 해당 HTML을 보여줌)
# ==========================================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/stats')
def stats():
    # '통계' 버튼을 누르면 stats.html을 보여줌!
    return render_template('stats.html')

@app.route('/settings')
def settings():
    # '설정' 버튼을 누르면 settings.html을 보여줌!
    return render_template('settings.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
