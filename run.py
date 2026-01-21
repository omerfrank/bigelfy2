from app import create_app

app = create_app()

if __name__ == '__main__':
    # [cite_start]Running on port 80 as defined in architecture [cite: 77]
    app.run(host='0.0.0.0', port=443, ssl_context='adhoc')
