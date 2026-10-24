# In 19Keys' house

Da Homi is the upgrade of the existing GitHub system, not a replacement:

- The github skill (`~/workspace/skills/github/`) is the authenticated hand: its `gh` CLI and operating rules apply to every search and fetch.
- The hunt engine (`~/workspace/.jarvis/github-hunt/hunt.py`, seen list, quality bar) and the three daily hunt jobs are Da Homi's scheduled mode: they keep scanning his lanes (AI video and motion, agent skills, creator tools, GTM and funnel systems, 3D globes) so the cache stays warm before he asks.
- Da Homi adds what the hunts never had: the on-demand reflex when a live task hits a wall, the safety vet, the fetch-test-finish loop, and the memory of mistakes.

## Host setup (v2.1)

The lines above say which tools Da Homi rides. This section says where the code it brings home runs. Three settings on the host keep a stranger's code away from everything that matters: a separate operating system user, an egress allowlist scoped to that user, and secrets injected per call instead of kept in any environment. None of the three is a script, and none of them depends on Da Homi remembering to check anything. They are configuration on the Mac Mini, or on a Linux machine, and the operating system enforces them on every run.

### Separate operating system user

Create a standard user named dahomi with no admin rights. On macOS, run sysadminctl as shown below, or open System Settings, go to Users and Groups, add a user, and leave the account type at Standard. On Linux, useradd creates the account and its home directory. No person logs in as dahomi. The agent reaches it through sudo, which checks the caller's credentials rather than the target's, so on Linux the account can keep the locked password that useradd gives it.

```
# macOS: a standard account (no -admin); a lone "-" after -password makes sysadminctl prompt for it
sudo sysadminctl -addUser dahomi -password -
sudo createhomedir -c -u dahomi          # only if /Users/dahomi did not appear

# Linux
sudo useradd -m dahomi
```

Keep Da Homi's working copy in dahomi's home. The scripts write their cache beside themselves, so with the folder in dahomi's home, every receipt, fetch, manifest, and trial record lands there and nowhere else. Then close the owner's home with chmod 700, so no other account can even list it. The macOS login keychain, the SSH keys in the owner's .ssh folder, and everything else under the owner's home belong to the owner's account alone, so dahomi cannot read any of it. On Linux, useradd can leave dahomi's own home closed to other accounts, so open it for reading with chmod 755 and the agent can read receipts and manifests. That costs nothing, because nothing valuable lives there.

```
# macOS; on Linux, the same commands with /home in place of /Users
sudo rsync -a --exclude da-homi-cache <path to the Da Homi folder>/ /Users/dahomi/da-homi/
sudo chown -R dahomi /Users/dahomi/da-homi
chmod 700 /Users/<owner>

# Linux only: let the agent read dahomi's receipts and manifests
sudo chmod 755 /home/dahomi
```

The agent runs fetch.py and trial.py as dahomi through a sudoers rule scoped to exactly those scripts. Write it with visudo, which refuses to save a file with a syntax error. The first rule line below is that grant. The second adds the hunt, and it is needed: run as dahomi, da_homi.py writes its receipts into dahomi's cache, where fetch.py running as dahomi can read them, while a receipt left in the owner's closed home would be out of its reach. Running the hunt as dahomi also makes it search with dahomi's own GitHub login, described below. The excuse gate only reads receipts, so the agent can run excuse_gate.py as itself from the same copy, and it will find what the hunt wrote.

```
# sudo visudo -f /etc/sudoers.d/dahomi
# put the owner's short user name in place of <owner>; on Linux the paths start with /home/dahomi
<owner> ALL=(dahomi) NOPASSWD: /usr/bin/python3 /Users/dahomi/da-homi/scripts/fetch.py *, /usr/bin/python3 /Users/dahomi/da-homi/scripts/trial.py *
<owner> ALL=(dahomi) NOPASSWD: /usr/bin/python3 /Users/dahomi/da-homi/scripts/da_homi.py hunt *
```

The agent then calls the scripts as shown next. The H option matters on macOS, whose stock sudo settings keep the caller's HOME. Without it, git, gh, and every trial would look for their settings in the owner's home instead of dahomi's. The interpreter path in each call must be the one the rule names.

```
sudo -H -u dahomi /usr/bin/python3 /Users/dahomi/da-homi/scripts/da_homi.py hunt "the missing capability"
sudo -H -u dahomi /usr/bin/python3 /Users/dahomi/da-homi/scripts/fetch.py owner/repo --receipt <receipt.json> --pin <sha>
sudo -H -u dahomi /usr/bin/python3 /Users/dahomi/da-homi/scripts/trial.py <fetched folder> -- <test command>
```

The dahomi user gets its own GitHub login, made with a fine grained personal access token that can only read public repositories. The hunt still authenticates and is not rate limited, yet nothing valuable sits behind the token, since anyone who took it could read only what the whole world can already read. Create it on GitHub under Settings, Developer settings, Personal access tokens, with repository access limited to public repositories and no permissions added, then hand it to gh as dahomi. If dahomi has no keychain to keep it in, gh stores the token in a plain file in dahomi's home, which is acceptable for a token this weak.

```
sudo -H -u dahomi gh auth login --with-token     # paste the token, then press Ctrl+D
sudo -H -u dahomi gh auth status
```

There is one caution about this layout. The dahomi account owns everything in its home, so code that runs as dahomi could also rewrite the copy of the scripts kept there, and a later run would report whatever that code wanted. The stricter version keeps the scripts in a folder owned by root, names that folder in the sudoers rule, and links only the cache into dahomi's home. The cache still lives there and stays writable, and the scripts do not.

```
# macOS paths; on Linux the cache folder is /home/dahomi/da-homi-cache
sudo rsync -a --exclude da-homi-cache <path to the Da Homi folder>/ /opt/da-homi/
sudo chown -R root /opt/da-homi && sudo chmod -R go-w /opt/da-homi
sudo mkdir -p /Users/dahomi/da-homi-cache && sudo chown dahomi /Users/dahomi/da-homi-cache
sudo ln -s /Users/dahomi/da-homi-cache /opt/da-homi/da-homi-cache
# then name /opt/da-homi/scripts/fetch.py, trial.py and da_homi.py in the sudoers rule
```

### Egress allowlist scoped to that user

Everything dahomi sends off the machine goes through one door: a small allowlisting HTTP proxy on localhost, with its access log on. The light choice is tinyproxy, from Homebrew on the Mac Mini or the distribution package on Linux, and squid does the same job with more configuration. The proxy listens on 127.0.0.1 port 8888, takes clients from this machine only, forwards only to hosts on its list, and logs every request it serves or refuses. Run it as its own unprivileged user. The Linux package already does. On macOS the stock configuration names the nobody user, and tinyproxy switches to it only when it starts as root, so start it as a system service with sudo.

```
# tinyproxy.conf: the stock file already sets User, Group, Port 8888 and Allow 127.0.0.1
# macOS: /opt/homebrew/etc/tinyproxy/tinyproxy.conf    Linux: /etc/tinyproxy/tinyproxy.conf
Listen 127.0.0.1
ConnectPort 443
Filter "/opt/homebrew/etc/tinyproxy/allowlist"
FilterDefaultDeny Yes
LogFile "/opt/homebrew/var/log/tinyproxy/tinyproxy.log"
LogLevel Info
# Linux: Filter "/etc/tinyproxy/allowlist", and keep the package's own User, Group and LogFile lines
```

The allowlist holds one anchored pattern per host, so a lookalike host cannot slip through on a partial match.

```
^github\.com$
^api\.github\.com$
^codeload\.github\.com$
^objects\.githubusercontent\.com$
^raw\.githubusercontent\.com$
^pypi\.org$
^files\.pythonhosted\.org$
^registry\.npmjs\.org$
# the owner's own services go here, one anchored host per line
```

```
# macOS: started as root so it can drop to nobody
sudo mkdir -p /opt/homebrew/var/log/tinyproxy && sudo chown nobody /opt/homebrew/var/log/tinyproxy
sudo brew services start tinyproxy
# Linux
sudo systemctl restart tinyproxy
```

Then block every other way out for dahomi at the packet filter. On macOS, pf can match packets by the user that owns the socket, so an anchor with two rules does it. The first lets dahomi reach the proxy, and the second blocks and logs everything else dahomi sends, to any host on any port, loopback included. Do not add a set skip line for lo0, or dahomi could reach other services listening on the machine. The pf firewall is off by default and stays off after a restart, so enable it at boot with a launch daemon that runs pfctl, and check the anchor after each macOS update, which can put back the stock pf.conf.

```
# /etc/pf.anchors/dahomi
pass out quick proto tcp from any to 127.0.0.1 port 8888 user dahomi
block out log quick proto {tcp udp} from any to any user dahomi

# add to the end of /etc/pf.conf
anchor "dahomi"
load anchor "dahomi" from "/etc/pf.anchors/dahomi"

# load, enable, confirm, and watch the blocked attempts
sudo pfctl -f /etc/pf.conf
sudo pfctl -e
sudo pfctl -a dahomi -s rules
sudo ifconfig pflog0 create
sudo tcpdump -n -e -ttt -i pflog0
```

On Linux, the iptables owner match does the same job, and nftables does it with a meta skuid match. Order matters: accept dahomi's connections to the proxy, log the rest, then reject them. Under iptables, IPv6 needs its own reject line. Save the rules so they survive a restart.

```
sudo iptables -A OUTPUT -m owner --uid-owner dahomi -d 127.0.0.1 -p tcp --dport 8888 -j ACCEPT
sudo iptables -A OUTPUT -m owner --uid-owner dahomi -j LOG --log-prefix "dahomi blocked: "
sudo iptables -A OUTPUT -m owner --uid-owner dahomi -j REJECT
sudo ip6tables -A OUTPUT -m owner --uid-owner dahomi -j REJECT
sudo netfilter-persistent save        # Debian and Ubuntu, from the iptables-persistent package
```

Point dahomi's programs at the proxy. Put the proxy variables in dahomi's shell profile for any shell opened as dahomi. Because sudo resets the environment and does not read that profile when it runs a single command, hand sudo the same values through an env_file bound to dahomi, which it adds to every command it runs as dahomi. Set both the lowercase and the uppercase names, because curl reads only the lowercase http_proxy while Python and most other tools accept either. Since trial.py inherits its environment by default, every trial, and every git, pip, npm, or gh call inside one, goes through the proxy with no change to any script.

```
# /etc/dahomi/proxy.env, created as root
# the same lines with export in front go in dahomi's ~/.zprofile or ~/.profile
http_proxy=http://127.0.0.1:8888
https_proxy=http://127.0.0.1:8888
HTTP_PROXY=http://127.0.0.1:8888
HTTPS_PROXY=http://127.0.0.1:8888
no_proxy=127.0.0.1,localhost
NO_PROXY=127.0.0.1,localhost

# add to /etc/sudoers.d/dahomi with visudo
Defaults>dahomi env_file=/etc/dahomi/proxy.env
```

Check the whole path once after setup. The first trial below must print the proxy variables, the second must return GitHub's headers, and the third must fail with a refusal from the proxy that also shows up in its log. If the first prints no proxy variables, the env_file line is not taking effect, and dahomi's requests fail closed at the firewall until it does.

```
sudo -H -u dahomi /usr/bin/python3 /Users/dahomi/da-homi/scripts/trial.py /tmp -- /usr/bin/env
sudo -H -u dahomi /usr/bin/python3 /Users/dahomi/da-homi/scripts/trial.py /tmp -- /usr/bin/curl -sSI https://api.github.com
sudo -H -u dahomi /usr/bin/python3 /Users/dahomi/da-homi/scripts/trial.py /tmp -- /usr/bin/curl -sSI https://example.com
```

This is enforced by the firewall, not by any script. A trial that honors the proxy variables reaches only the hosts on the list, and a trial that ignores them and dials out directly hits the packet filter and goes nowhere. The proxy's access log is the behavioral receipt: any attempt to reach a host off the list is both blocked and recorded, by the proxy when the attempt goes through it and by the firewall log when it tries to go around. One limit is worth knowing. On macOS, name lookups go through a system resolver that runs as its own user, so a lookup by name can still leave the machine even when dahomi's own packets cannot. That channel is narrow, and the next mechanism is what makes it close to worthless, because there is nothing in dahomi's environment to send.

### Per call secret injection

No long lived token is exported in a shell profile or in the agent's base environment. A token that sits in an environment variable all day can be read by every process started from that shell, third party code included. Secrets stay in a store and are read at the moment one command needs them, into that command alone. On macOS the store is the Keychain, and the security command reads a generic password inline at call time. A vault CLI does the same for everything else: 1Password's op run resolves the secret references in a template file and injects the values into one process only. On Linux, the libsecret command line tool reads from the desktop keyring, and pass reads from a store encrypted with gpg.

```
# macOS Keychain: store once (a trailing -w prompts for the value), then read inline, per call
security add-generic-password -s <service> -a <account> -w
API_KEY="$(security find-generic-password -w -s <service> -a <account>)" python3 <tool>

# 1Password: the template holds references such as API_KEY=op://<vault>/<item>/credential, never values
op run --env-file=<template> -- python3 <tool>

# Linux: libsecret, or pass
API_KEY="$(secret-tool lookup service <service> account <account>)" python3 <tool>
API_KEY="$(pass show <service>/<account>)" python3 <tool>
```

The gh CLI already works this way for GitHub. It keeps its token in the keychain or the system keyring and hands it out per call, and hub_search.py asks gh for it at the moment of each search rather than reading an exported variable. Leave GITHUB_TOKEN unset, since hub_search.py falls back to it only when gh is missing.

The house env file of API keys stays in the owner's home, unreadable by dahomi, and is loaded only into the single process that needs it, never into the agent's session. The parentheses below start a subshell, so the variables exist for that one process and end with it.

```
( set -a; . <house env file>; set +a; exec python3 <the one tool that needs the keys> )
```

The result is that the dahomi environment where third party code runs holds nothing worth taking, not because a trial scrubbed it but because it was never there. That is also why trials keep their full environment by default: on this host, the full environment of dahomi holds paths and proxy settings and nothing else.

The hard provenance floor, which would let fetch.py refuse a repository that falls below a metadata floor, and the canary planter, which would plant decoy credentials that report whatever touches them, are held for a later pass by the owner's decision. Until then provenance flags inform and never refuse, and nothing in this section depends on either piece.
