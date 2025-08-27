FROM nginx:alpine

# Remove the default Nginx configuration file.
RUN rm /etc/nginx/conf.d/default.conf

# Copy the custom configuration file from the build context to the container.
COPY nginx.conf /etc/nginx/conf.d/

