from flask import Flask, jsonify, request
import os

app = Flask(__name__)

# 这是一个测试接口，用来确认服务器是否在运行
@app.route('/')
def index():
    return "游戏服务器正在运行！"

# TODO: 未来在这里实现 /api/login 接口
@app.route('/api/login', methods=['POST'])
def login():
    # 这里的逻辑需要你根据API蓝图来实现
    return jsonify({"status": 404, "message": "登录功能待实现"})

# TODO: 未来在这里实现 /api/battle/start 接口
@app.route('/api/battle/start', methods=['POST'])
def handle_battle():
    # 暂时先返回一个固定的胜利模板
    victory_response = {
        "result": "victory",
        "exp_gained": 99999,
        "gold_gained": 88888,
    }
    return jsonify(victory_response)

if __name__ == '__main__':
    # 本地测试时，使用5000端口
    app.run(port=5000, debug=True)