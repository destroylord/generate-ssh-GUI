from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import subprocess
import os
from pathlib import Path

app = Flask(__name__)
app.secret_key = 'dev'  # Ganti di production

SSH_DIR = Path.home() / ".ssh"
SSH_CONFIG = SSH_DIR / "config"
os.makedirs(SSH_DIR, exist_ok=True)

def list_keys():
    return [f.stem for f in SSH_DIR.glob("*.pub")]

def delete_key(alias):
    priv = SSH_DIR / alias
    pub = SSH_DIR / f"{alias}.pub"
    if priv.exists(): priv.unlink()
    if pub.exists(): pub.unlink()

    if SSH_CONFIG.exists():
        lines = SSH_CONFIG.read_text().splitlines()
        new_lines = []
        skip = False
        for line in lines:
            if line.strip().startswith("Host ") and alias in line:
                skip = True
            if skip and line.strip() == "":
                skip = False
                continue
            if not skip:
                new_lines.append(line)
        SSH_CONFIG.write_text("\n".join(new_lines))

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        alias = request.form["alias"].strip()
        hostname = request.form["hostname"].strip()
        user = request.form["user"].strip()
        key_path = SSH_DIR / alias

        try:
            subprocess.run([
                "ssh-keygen", "-t", "ed25519", "-f", str(key_path), "-N", ""
            ], check=True)

            config_entry = f"""
Host {alias}
    HostName {hostname}
    User {user}
    IdentityFile {key_path}
"""
            with open(SSH_CONFIG, "a") as f:
                f.write(config_entry)

            flash(f"SSH key '{alias}' berhasil dibuat dan config ditambahkan.", "success")
        except subprocess.CalledProcessError as e:
            flash(f"Gagal membuat key: {str(e)}", "error")

    keys = list_keys()
    return render_template("index.html", keys=keys)

@app.route("/delete/<alias>")
def delete(alias):
    delete_key(alias)
    flash(f"Key '{alias}' berhasil dihapus.", "info")
    return redirect(url_for('index'))

@app.route("/copy", methods=["POST"])
def copy_key():
    alias = request.form["alias"]
    remote = request.form["remote"]
    port = request.form["port"]

    pub_key_path = SSH_DIR / f"{alias}.pub"
    if not pub_key_path.exists():
        flash(f"Key '{alias}' tidak ditemukan.", "error")
        return redirect(url_for('index'))

    try:
        subprocess.run([
            "ssh-copy-id", "-i", str(pub_key_path), f"-p{port}", remote
        ], check=True)
        flash(f"Key '{alias}' berhasil dikirim ke {remote}.", "success")
    except subprocess.CalledProcessError as e:
        flash(f"Gagal copy key: {str(e)}", "error")
    return redirect(url_for('index'))

@app.route("/clone", methods=["POST"])
def clone_repo():
    alias = request.form["alias"]
    repo_url = request.form["repo_url"]
    clone_dir = request.form["clone_dir"]
    target_folder = request.form["target_folder"]
    
    # Auto-generate folder name if not provided
    if not clone_dir:
        repo_name = repo_url.split('/')[-1].replace('.git', '')
        clone_dir = repo_name
    
    # Set target directory
    if target_folder:
        # Ensure target folder exists
        os.makedirs(target_folder, exist_ok=True)
        full_clone_path = os.path.join(target_folder, clone_dir)
    else:
        full_clone_path = clone_dir
    
    # Check if SSH key exists
    private_key_path = SSH_DIR / alias
    if not private_key_path.exists():
        flash(f"❌ SSH key '{alias}' tidak ditemukan. Pastikan key sudah dibuat terlebih dahulu.", "error")
        return redirect(url_for('index'))
    
    env = os.environ.copy()
    # Use proper SSH command with StrictHostKeyChecking=no for first time connections
    env['GIT_SSH_COMMAND'] = f'ssh -i "{private_key_path}" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'

    try:
        result = subprocess.run(["git", "clone", repo_url, full_clone_path], 
                              check=True, env=env, capture_output=True, text=True)
        
        # Get absolute path of cloned directory
        clone_path = os.path.abspath(full_clone_path)
        
        flash(f"✅ Repository cloned successfully!\n📁 Location: {clone_path.replace(os.sep, '/')}\n🔗 Repository URL: {repo_url}", "success")
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        flash(f"❌ Gagal clone repo: {error_msg}", "error")
    return redirect(url_for('index'))

@app.route("/show/<alias>")
def show_key(alias):
    pub_key_path = SSH_DIR / f"{alias}.pub"
    if not pub_key_path.exists():
        return jsonify({"error": f"Key '{alias}' tidak ditemukan."}), 404
    
    try:
        key_content = pub_key_path.read_text().strip()
        return jsonify({
            "alias": alias,
            "key_content": key_content,
            "success": True
        })
    except Exception as e:
        return jsonify({"error": f"Gagal membaca key: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True)
