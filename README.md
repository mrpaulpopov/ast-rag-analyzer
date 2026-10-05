
docker-compose up -d
docker-compose run --rm --build app python src/pipelines/training_pipeline.py
docker-compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm --build app python src/pipelines/training_pipeline.py
docker-compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm --build app python src/pipelines/update_pipeline.py
docker-compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm --build app python src/pipelines/inference_pipeline.py

docker-compose down -v