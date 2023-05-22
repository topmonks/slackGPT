from slackgpt.main import SlackGPT

if __name__ == '__main__':
    # Signals (SIGINT, SIGTERM) are handled by slack webrunner and because of
    # retarded implementation we cannot override signal handling, and in the end
    # I CBA to monkeypatch it
    sgpt = SlackGPT()
    sgpt.start()
