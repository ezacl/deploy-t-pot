# deploy-t-pot
> Fabric scripts to automate distributed T-Pot deployment process

## Description:

- This repository will allow you to set up a distributed version of the [T-Pot honeypot project](https://github.com/telekom-security/tpotce)
- It will first set up a central logging server with Elasticsearch and Kibana to store all the honeypot data
- It will then set up any number of T-Pot sensor servers which will securely send their data to the central logging server
- This architecture is based off of [this comment](https://github.com/telekom-security/tpotce/issues/437#issuecomment-521623873), but has been updated to be more robust and compatible with the latest ELK versions.

## Installation:

### Create Servers:

- First, you must to create all the servers to use through your cloud provider's dashboard. This project has been tested with DigitalOcean, but will most likely work with other providers
- Logging server: Debian 10, ≥ 8 GB RAM, ≥ 64 GB disk space
- Sensor servers: Debian 10, ≥ 4 GB RAM, ≥ 64 GB disk space
- Once all servers are up, you must create a DNS A record for your central logging server (recommended to do so for each sensor server too)
  - This is usually done through your cloud provider's dashboard
- Make sure that you have root access to each server

### Run Scripts:

- Clone repository on your local machine: `git clone https://github.com/ezacl/deploy-t-pot`
- Navigate into project directory
- Install dependencies: `pip install -r requirements.txt`
- Copy `credentials.json.template` into a file named `credentials.json` and fill in server credentials
  - `logging.host` should be the domain name that you would use to SSH into the server, configured through the DNS A record previously set up
    - So if you would SSH into the logging server with `ssh root@subdomain.mydomain.com`, then `logging.host` would be `"subdomain.mydomain.com"`
    - Note that this project does not yet support users other than `root` for any of the servers
  - `logging.email` should be the email address to give to Certbot for notifications about SSL certificates expiring, etc.
  - Add a new object in the `sensors` array for each sensor server you would like to set up and fill in the `host` field for each
    - The `host` field may be a raw IP address if you did not set up DNS records for the sensor servers, but it is recommended to create A records for each sensor
- Run `python3 fabfile.py` to configure the logging server and all sensor servers defined in `credentials.json`. The entire process will take ~10 minutes for the logging server + ~10 minutes for each sensor server, and logs will be written to `deployment.log`
- Once the script finishes, you can access the logging server's Kibana dashboard at https://your.chosen.domain.com:5601
  - Log in with user `elastic` and the password for the user written in `passwords.txt`
- Go to Analytics > Dashboard > T-Pot to see attack data visualizations

## Troubleshooting:

- You may have to wait a few minutes for Logstash to start up on the sensor servers and begin sending attack data to the logging server
- Elasticsearch is accessible on the logging server at https://your.chosen.domain.com:64298, and you can use user `elastic` and its password to authenticate
- Elasticsearch/Kibana config files are at /etc/elasticsearch/elasticsearch.yml and /etc/kibana/kibana.yml on the logging server
- Elasticsearch/Kibana logs are at /var/log/elasticsearch/ and /var/log/kibana/ on the logging server
- T-Pot changes the SSH port to port 64295 during installation, so make sure to use `ssh -P 64295 root@subdomain.mydomain.com` to SSH into sensor servers
- logstash.conf is at /data/elk/logstash.conf on the sensor servers
- Sending data from sensor servers to logging server through Logstash can often be the source of issues, so check logstash logs with `docker logs logstash` on the sensor servers
- T-Pot docker-compose file is at /opt/tpot/etc/tpot.yml on the sensor servers
