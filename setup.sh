sudo pip3 install -r requirements.txt
sudo cp agents_pregnancy.conf /etc/supervisor/conf.d/
sudo cp agents_pregnancy_nginx.conf /etc/nginx/sites-enabled/
sudo supervisorctl update
sudo systemctl restart nginx
sudo certbot --nginx -d pregnancy.medsenger.ru