#!/bin/bash
set -e

# restart apache
sudo systemctl restart httpd

# restart cron
sudo systemctl start crond
