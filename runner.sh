#!/bin/bash

echo "Сборка образа Docker..."
sudo docker build -t bot .

# shellcheck disable=SC2181
if [ $? -ne 0 ]; then
  echo "Ошибка: Сборка образа Docker не удалась."
  exit 1
fi

echo "Запуск контейнера Docker..."
sudo docker run --env-file .env bot

# shellcheck disable=SC2181
if [ $? -ne 0 ]; then
  echo "Ошибка: Запуск контейнера не удался."
  exit 1
fi
