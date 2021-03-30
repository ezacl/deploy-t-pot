# deploy-t-pot
> Fabric scripts to automate distributed T-Pot deployment process

## Description:

- This repository will allow you to set up a distributed version of the [T-Pot honeypot project](https://github.com/telekom-security/tpotce)
- It will first set up a central logging server with Elasticsearch and Kibana to store all the honeypot data
- It will then set up any number of T-Pot sensor servers which will securely send their data to the central logging server
- This architecture is based off of [this comment](https://github.com/telekom-security/tpotce/issues/437#issuecomment-521623873), but has been updated to be more robust and compatible with the latest ELK versions.
- You will need to use a deployment server to run these scripts, as the SSL certificate logic runs locally (including renewal)

## Installation:

### Create Deployment Server:

- First, you must create all the deployment server through your cloud provider's dashboard. This project currently only supports DigitalOcean, but will hopefully work with other providers in the future
- Deployment server: Debian 10, ≥ 2 GB RAM, not much disk space needed
- Create a non-root user with sudo privileges to run the deployment scripts: `adduser --gecos "" deploymentuser` and `usermod -aG sudo deploymentuser`
- Check that you have Python ≥ 3.7 installed, then also install git and pip with `sudo apt-get --yes install git python3-pip`
- Upgrade pip: `pip3 install --upgrade pip`
- Clone repository: `git clone https://github.com/ezacl/deploy-t-pot`
- Navigate into project directory
- Install dependencies: `pip3 install -r requirements.txt` (NOTE: using a virtual environment is not supported yet, as it will break the SSL certificate renewal script.)
- Create SSH keys: `ssh-keygen -f ~/.ssh/id_rsa -t rsa -b 4096 -N ''`
- Copy the contents of `~/.ssh/id_rsa.pub` to add it to the logging server and each sensor server

### Create Network Servers:

- Now, create all the network servers to use through your cloud provider's dashboard
- Logging server: Debian 10, ≥ 8 GB RAM, ≥ 64 GB disk space
- Sensor servers: Debian 10, ≥ 4 GB RAM, ≥ 64 GB disk space
- Make sure that you have root access to each server
- You must add the SSH key generated on the deployment server for the root user in each of the network servers, as password authentication is not supported
- Once all servers are up, you must create a DNS A record for your central logging server (recommended to do so for each sensor server too)
  - This is usually done through your cloud provider's dashboard

### Run Scripts:

- Wait until all network servers are up and running
- On deployment server, navigate into project directory
- Rename `credentials.json.template` to `credentials.json` and fill in server credentials
  - `sudouser` is name to use for non-root sudo user on all network servers. Can leave as default
  - `deployment.sudopass` is sudo password for non-root user who will be running the deployment scripts on the deployment server (that you chose when running `adduser --gecos "" deploymentuser`)
  - `deployment.email` should be the email address to give to Certbot for notifications about SSL certificates expiring, etc.
  - `logging.host` should be the domain name that you would use to SSH into the server, configured through the DNS A record previously set up
    - So if you would SSH into the logging server with `ssh root@subdomain.mydomain.com`, then `logging.host` would be `"subdomain.mydomain.com"`
    - Note that this project will create a non-root sudo user (username specified by `sudouser`) in each of the servers, but needs root access initially to create them
  - `logging.sudopass` should be the sudo password you would like to use for the above user
  - Add a new object in the `sensors` array for each sensor server you would like to set up and fill in the `host` and `sudopass` fields for each
    - The `host` field may be a raw IP address if you did not set up DNS records for the sensor servers, but it is recommended to create A records for each sensor
- Rename `digitalocean.ini.template` to `digitalocean.ini` and fill in your DigitalOcean API key
- Run `python3 fabfile.py` (NOTE: must be in the project directory! Don't run something like `python3 deploy-t-pot/fabfile.py` from outside the directory) to configure the logging server and all sensor servers defined in `credentials.json`. The entire process will take ~10 minutes for the logging server + ~10 minutes for each sensor server, and logs will be written to `deployment.log`
- Once the script finishes, you can access the logging server's Kibana dashboard at https://your.chosen.domain.com:5601
  - Log in with user `elastic` and the password for the user written in `passwords.txt` on the deployment server
- Go to Analytics > Dashboard > T-Pot to see attack data visualizations

## Troubleshooting:

- You may have to wait a few minutes for Logstash to start up on the sensor servers and begin sending attack data to the logging server
- This project disables root login and password authentication on all servers, so you can only SSH into the servers using an SSH key and the `tpotadmin` user
- Elasticsearch is accessible on the logging server at https://your.chosen.domain.com:64298, and you can use user `elastic` and its password to authenticate
- Elasticsearch/Kibana config files are at `/etc/elasticsearch/elasticsearch.yml` and `/etc/kibana/kibana.yml` on the logging server
- Elasticsearch/Kibana logs are at `/var/log/elasticsearch/` and `/var/log/kibana/` on the logging server
- elasticsearch-curator logs are at `/var/log/curator/` on the logging server
- T-Pot changes the SSH port to port 64295 during installation, so make sure to use `ssh -p 64295 tpotadmin@subdomain.mydomain.com` to SSH into sensor servers
- logstash.conf is at `/data/elk/logstash.conf` on the sensor servers
- Sending data from sensor servers to logging server through Logstash can often be the source of issues, so check logstash logs with `docker logs logstash` on the sensor servers
- T-Pot docker-compose file is at `/opt/tpot/etc/tpot.yml` on the sensor servers
- Can force SSL certificate renewal with `sudo certbot renew --force-renewal` on deployment server to see if the renewal hook (`/etc/letsencrypt/renewal-hooks/deploy/updateCerts.sh`) copies the certificates to all of the network servers correctly, but BE CAREFUL that this can cause you to quickly exceed the 5 certificate renewals per week limit that Certbot imposes
- Certbot logs are at `/var/log/letsencrypt/` on the deployment server
