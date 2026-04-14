from app import create_app, socketio

app = create_app()

if __name__ == "__main__":
    # Change host to 0.0.0.0 so other devices on the same network can connect
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)
