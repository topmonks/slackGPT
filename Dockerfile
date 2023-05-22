FROM python:3.8-slim-buster
WORKDIR /app
COPY ./slackgpt /app/slackgpt
COPY ./slackgpt.py /app/
COPY ./requirements.txt /app/
RUN pip install --trusted-host pypi.python.org -r requirements.txt
EXPOSE 3000
CMD ["python", "slackgpt.py"]