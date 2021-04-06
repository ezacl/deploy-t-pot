# deploy-t-pot
> Fabric scripts to automate distributed T-Pot deployment process

## Description:

- This repository will allow you to set up a distributed version of the [T-Pot honeypot project](https://github.com/telekom-security/tpotce)
- It will first set up a central logging server with Elasticsearch and Kibana to store all the honeypot data
- It will then set up any number of T-Pot sensor servers which will securely send their data to the central logging server
- This architecture is based off of [this comment](https://github.com/telekom-security/tpotce/issues/437#issuecomment-521623873), but has been updated to be more robust and compatible with the latest ELK versions.
- You will need to use a deployment server to run these scripts, as the SSL certificate logic runs locally (including renewal)
- This project currently only supports DigitalOcean as it creates all the network servers through the DigitalOcean API, but will hopefully support other cloud providers in the future
- You will need to have already set up a domain in DigitalOcean, as well as have access to an API key for your account

## Features:

- Fully automated setup of a honeypot network with any number of sensor servers securely sending their data to a central logging server
- Custom [T-Pot Sensor](https://github.com/telekom-security/tpotce#sensor) installation ([T-Pot fork here](https://github.com/ezacl/tpotce-light)) on each sensor server including Logstash to send data to central logging server
- Programmatic creation of all DigitalOcean droplets for honeypot network, including setup of DNS A records for each droplet
- Complete SSL certificate setup for the logging server using Let's Encrypt/Certbot, including automatic renewals run by the deployment server
- Automatic deletion of Elasticsearch indices after 7 days using elasticsearch-curator (can easily change this value)
- Automatic configuration of Kibana dashboard on logging server to have all data visualizations available in a [vanilla T-Pot deployment](https://github.com/telekom-security/tpotce#kibana-dashboard)
- Creation of non-root sudo user on each network server and disabling of SSH root login and password authentication for security
- Only one Python script to run after having pip installed dependencies on deployment server for everything to be set up
- Complete teardown script to clean up entire network in one command

## Installation:

### Create Deployment Server:

- First, you must create the deployment server through the DigitalOcean dashboard
- Deployment server: Debian 10, ≥ 1 GB RAM, ≥ 10 GB disk space
- Create a non-root user with sudo privileges to run the deployment scripts: `adduser --gecos "" deploymentuser` and `usermod -aG sudo deploymentuser`
- Stop your root SSH session and log in again as the created user (`deploymentuser` from the line above)
- Check that you have Python ≥ 3.7 installed, then also install git and pip with `sudo apt-get --yes install git python3-pip`
- Upgrade pip: `pip3 install --upgrade pip`
- Clone repository: `git clone https://github.com/ezacl/deploy-t-pot`
- Navigate into project directory
- Install dependencies: `pip3 install -r requirements.txt` (NOTE: using a virtual environment is not supported yet, as it will break the SSL certificate renewal script)

### Edit Config Files:

- Make sure you are in the project directory
- Rename `credentials.json.template` to `credentials.json` and fill in server credentials
  - `sudouser` is the name to use for the non-root sudo user on all network servers. Can leave it as default
  - `deployment.sudopass` is the sudo password for the non-root user who will be running the Fabric scripts on the deployment server (that you chose when running `adduser --gecos "" deploymentuser`)
  - `deployment.email` should be the email address to give to Certbot for notifications about SSL certificates expiring, etc.
  - `logging.host` should be the full domain name that you would like for the logging server
    - This must be a sub-domain of the top-level domain that you already have registered in DigitalOcean. For example, if you'd like to use `logger.mydomain.com`, you must already have `mydomain.com` as a registered domain in DigitalOcean
    - Note that this project will create a non-root sudo user (username specified by `sudouser`) in each of the network servers
  - `logging.sudopass` should be the sudo password you would like to use for the above user
  - Add an object in the `sensors` array for each sensor server you would like to set up and fill in the `host` and `sudopass` fields for each
    - The `host` field follows the same rules as the `logging.host` field (i.e. it must be a sub-domain of one of your domain names)
- Rename `digitalocean.ini.template` to `digitalocean.ini` and replace `YOUR_API_TOKEN_HERE` with your DigitalOcean API key

### Run Scripts:

- Run `python3 fabfile.py` (NOTE: must be in the project directory! Don't run something like `python3 deploy-t-pot/fabfile.py` from outside the directory) to create and configure the logging server and all sensor servers defined in `credentials.json`. The entire process will take ~10 minutes for the logging server + ~10 minutes for each sensor server, and logs will be written to `deployment.log`
  - NOTE: This will, as explained, spin up as many DigitalOcean droplets as are specified in `credentials.json`. The logging server currently costs $0.06/hour, and each sensor server costs $0.03/hour. Please keep in mind that these droplets will be created without asking for confirmation!
- Once the script finishes, you can access the logging server's Kibana dashboard at https://your.chosen.domain.com:5601 (where `your.chosen.domain.com` is the value of `logging.host` in `credentials.json`)
  - Log in with user `elastic` and the password for the user written in `passwords.txt` on the deployment server
- Go to Analytics > Dashboard > T-Pot to see attack data visualizations

## Teardown:

- Run `python3 destroyNetwork.py` to cleanly tear down entire T-Pot network (including SSH keys, DNS records, and DigitalOcean droplets) through DigitalOcean API
  - Be careful that this will destroy the entirety of your deployment (except for the deployment server from which you are running the script) without asking for confirmation!

## Testing:

- Run unit test suite with `pytest` from anywhere inside the project directory

## Troubleshooting:

- You may have to wait a few minutes for Logstash to start up on the sensor servers and begin sending attack data to the logging server
- This project disables root login and password authentication on all network servers, so you can only SSH into the servers using the SSH key generated on your deployment server (`~/.ssh/id_rsa`) and the user defined by the `sudouser` key in `credentials.json`
- Elasticsearch is accessible on the logging server at https://your.chosen.domain.com:64298, and you can use user `elastic` and its password to authenticate
- Elasticsearch/Kibana config files are at `/etc/elasticsearch/elasticsearch.yml` and `/etc/kibana/kibana.yml` on the logging server
- Elasticsearch/Kibana logs are at `/var/log/elasticsearch/` and `/var/log/kibana/` on the logging server
- elasticsearch-curator logs are at `/var/log/curator/` on the logging server
  - Change the number of days before deleting old Elasticsearch indices by editing `configFiles/curatorActions.yml` before running the deployment, or `/opt/elasticsearch-curator/curatorActions.yml` on the logging server after the deployment
  - In either case, just change `unit_count` to the desired value
  - Completely disable deletion of old Elasicsearch indices by removing the last line of `/etc/crontab` on the logging server (the one that runs the `curator` command as root)
- T-Pot changes the SSH port to port 64295 during installation, so make sure to use `ssh -p 64295 tpotadmin@subdomain.mydomain.com` to SSH into sensor servers
- logstash.conf is at `/data/elk/logstash.conf` on the sensor servers
- Sending data from sensor servers to logging server through Logstash can often be the source of issues, so check logstash logs with `sudo docker logs logstash` on the sensor servers
- T-Pot docker-compose file is at `/opt/tpot/etc/tpot.yml` on the sensor servers
- Can force SSL certificate renewal with `sudo certbot renew --force-renewal` on deployment server to see if the renewal hook (`/etc/letsencrypt/renewal-hooks/deploy/updateCerts.sh`) copies the certificates to all of the network servers correctly, but BE CAREFUL that this can cause you to quickly exceed the 5 certificate renewals per week limit that Certbot imposes
  - This script should normally automatically run when the SSL certificates are within 30 days of their expiration
- Certbot logs are at `/var/log/letsencrypt/` on the deployment server
