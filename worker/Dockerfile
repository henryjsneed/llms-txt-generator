FROM public.ecr.aws/lambda/python:3.12

COPY pyproject.toml ${LAMBDA_TASK_ROOT}/
COPY src/ ${LAMBDA_TASK_ROOT}/src/

RUN pip install --no-cache-dir ${LAMBDA_TASK_ROOT}/

CMD ["llms_txt_worker.handler.lambda_handler"]
