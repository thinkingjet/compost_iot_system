# NGINX setup (Ubuntu VM)

Replace `example.com` with your domain in `compostiq.conf` and in the commands below.
The domain's DNS A record must point at the VM, and ports 80 and 443 must be open.

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
sudo certbot certonly --nginx -d example.com        # get the cert first
sudo cp compostiq.conf /etc/nginx/sites-available/compostiq.conf
sudo ln -s /etc/nginx/sites-available/compostiq.conf /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
sudo certbot renew --dry-run                        # confirm auto-renewal works
```

The apps must listen on `127.0.0.1` only, so the outside world reaches them through NGINX.
