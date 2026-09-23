# NGINX setup (Ubuntu VM)

The site is served on two subdomains: `dashboard.compostiq.win` and `api.compostiq.win`.
Both need DNS A records pointing at the VM, and ports 80 and 443 must be open.

If DNS is on Cloudflare, set both records to **DNS only** (grey cloud) while requesting the certificate.
Afterwards you can turn the proxy back on, but set Cloudflare's SSL/TLS mode to **Full (strict)**.
The **Flexible** mode causes an endless redirect loop with this config.

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
sudo certbot certonly --nginx -d dashboard.compostiq.win -d api.compostiq.win   # get the cert first
sudo cp compostiq.conf /etc/nginx/sites-available/compostiq.conf
sudo ln -s /etc/nginx/sites-available/compostiq.conf /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
sudo certbot renew --dry-run                        # confirm auto-renewal works
```

The apps must listen on `127.0.0.1` only, so the outside world reaches them through NGINX.

## Fresh reinstall

Use this to wipe NGINX and start clean. Let's Encrypt certificates live in `/etc/letsencrypt`, which this does not touch.

```bash
# 1. Back up the current config, just in case
sudo tar czf ~/nginx-backup-$(date +%F).tgz /etc/nginx

# 2. Stop and remove NGINX completely, including its config
sudo systemctl stop nginx
sudo apt purge -y nginx nginx-common nginx-core python3-certbot-nginx
sudo apt autoremove -y
sudo rm -rf /etc/nginx              # purge leaves behind files it didn't install

# 3. Reinstall
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
sudo mkdir -p /var/www/html
sudo systemctl enable --now nginx
curl -I http://localhost            # expect HTTP 200 from the welcome page

# 4. Certificate: skip certonly if one already exists for your domain
sudo certbot certificates
sudo certbot certonly --nginx -d dashboard.compostiq.win -d api.compostiq.win

# 5. Install the site, then run the setup commands above from the cp step onward
```
