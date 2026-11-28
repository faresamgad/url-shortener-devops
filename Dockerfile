FROM python:3.12-slim
WORKDIR /code
COPY app/requirements.txt . 
RUN pip install -r requirements.txt
COPY /app/ .
RUN useradd --system --no-create-home appuser
USER appuser
EXPOSE 8000
CMD [ "uvicorn", "main:app" , "--host", "0.0.0.0", "--port", "8000"]