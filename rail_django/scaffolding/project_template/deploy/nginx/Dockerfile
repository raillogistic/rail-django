FROM nginx:1.25-alpine

# Custom Nginx main config for worker tuning
RUN echo 'worker_processes auto;' > /etc/nginx/nginx.conf && \
    echo 'worker_rlimit_nofile 65536;' >> /etc/nginx/nginx.conf && \
    echo '' >> /etc/nginx/nginx.conf && \
    echo 'events {' >> /etc/nginx/nginx.conf && \
    echo '    worker_connections 4096;' >> /etc/nginx/nginx.conf && \
    echo '    multi_accept on;' >> /etc/nginx/nginx.conf && \
    echo '    use epoll;' >> /etc/nginx/nginx.conf && \
    echo '}' >> /etc/nginx/nginx.conf && \
    echo '' >> /etc/nginx/nginx.conf && \
    echo 'http {' >> /etc/nginx/nginx.conf && \
    echo '    include /etc/nginx/mime.types;' >> /etc/nginx/nginx.conf && \
    echo '    default_type application/octet-stream;' >> /etc/nginx/nginx.conf && \
    echo '    sendfile on;' >> /etc/nginx/nginx.conf && \
    echo '    tcp_nopush on;' >> /etc/nginx/nginx.conf && \
    echo '    tcp_nodelay on;' >> /etc/nginx/nginx.conf && \
    echo '    reset_timedout_connection on;' >> /etc/nginx/nginx.conf && \
    echo '    types_hash_max_size 2048;' >> /etc/nginx/nginx.conf && \
    echo '    server_names_hash_bucket_size 64;' >> /etc/nginx/nginx.conf && \
    echo '    include /etc/nginx/conf.d/*.conf;' >> /etc/nginx/nginx.conf && \
    echo '}' >> /etc/nginx/nginx.conf

COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY deploy/nginx/certs/ /etc/nginx/certs/
