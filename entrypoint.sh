#!/bin/bash

# Apply database migrations
./wait-for-it.sh db:5432 -- echo "Checking for config file"

# Create config file if it doesn't exist
if [ ! -f pictor/config.py ]; then
    cp pictor/config.py.example pictor/config.py
fi

echo "Apply database migrations"
python manage.py migrate

#Start server
echo "Starting server"
python manage.py runserver 0.0.0.0:8012
