import os
from datetime import datetime
from ruamel.yaml import YAML
from xml.etree import ElementTree as ET
from dotenv import load_dotenv

def get_bandwidth_usage():
    vnstat = os.popen('vnstat --xml m').read()

    tree = ET.fromstring(vnstat)
    traffic = tree.find("interface").find("traffic")

    current_year = datetime.now().year
    current_month = datetime.now().month
    current_day = datetime.now().day
    rx = tx = 0

    for month_data in traffic.find("months").iter("month"):
        date = month_data.find("date")
        if date is None:
            continue
        year_node = date.find("year")
        month_node = date.find("month")
        if year_node is None or month_node is None:
            continue
        if (int(year_node.text) == current_year and 
            int(month_node.text) == current_month):
            rx = int(month_data.find("rx").text)
            tx = int(month_data.find("tx").text)
            break
            
    total = rx + tx

    total = round(total / 1024 / 1024 / 1024, 2)

    if current_day == 1:
        yesterday = 0
    else:
        with open('/tmp/vnstat_subscribe_tmp', 'r') as f:
            yesterday = float(f.read())
    today = total - yesterday

    # 写入文件
    with open('/tmp/vnstat_subscribe_tmp', 'w') as f:
        f.write(str(total))

    return total, today

def update_yaml_file():
    # 解析yaml文件
    yaml = YAML()
    with open('subscribe.yaml', 'r') as f:
        config = yaml.load(f)

    # 更新yaml文件
    total, today = get_bandwidth_usage()
    config['proxies'][0]['name'] = str(datetime.now().month) + '月流量: ' +  str(total) + ' GB'
    config['proxies'][1]['name'] = '昨日使用流量: ' +  str(today) + ' GB'
    config['proxies'][2]['name'] = str(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    # 写入yaml文件
    with open('subscribe.yaml', 'w') as f:
        yaml.dump(config, f)

def git_upload(commit_message=None):
    """
    使用PyGithub将当前目录的更改推送到远程GitHub仓库
    
    参数:
        commit_message: 自定义提交信息，默认为"update subscription"
    """
    try:
        from github import Github, GithubException, Auth
        import os
        from datetime import datetime
        
        # 加载认证信息
        access_token = os.getenv('GITHUB_TOKEN')
        username = os.getenv('GITHUB_USERNAME')
        repo_name = os.getenv('GITHUB_REPO')  # 格式为"username/repo"
        
        auth = Auth.Token(access_token)

        if not all([access_token, username, repo_name]):
            raise ValueError("缺少必要的环境变量配置")

        # 设置默认提交信息
        if commit_message is None:
            commit_message = f"update subscription - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        # 连接GitHub
        g = Github(auth=auth)

        print(g.get_user().login)
        
        # 获取仓库对象
        repo = g.get_user(username).get_repo(repo_name)
        
        # 获取默认分支
        default_branch = repo.default_branch
        ref = repo.get_git_ref(f'heads/{default_branch}')
        
        # 获取当前commit
        current_commit = repo.get_commit(ref.object.sha)
        base_tree = current_commit.commit.tree
        
        # 准备文件更新列表
        element_list = []
        
        # 遍历当前目录下的所有文件
        for root, dirs, files in os.walk('.'):
            for file in files:
                if file.startswith('.') or file == '.env':
                    continue
                    
                file_path = os.path.join(root, file)
                if file_path.startswith('./'):
                    file_path = file_path[2:]
                    
                with open(file_path, 'rb') as f:
                    content = f.read()
                    
                # 创建blob
                blob = repo.create_git_blob(content.decode('utf-8'), 'utf-8')
                element = {
                    'path': file_path,
                    'mode': '100644',
                    'type': 'blob',
                    'sha': blob.sha
                }
                element_list.append(element)
        
        # 创建新的tree
        new_tree = repo.create_git_tree(element_list, base_tree)
        
        # 创建新的commit
        parent = [repo.get_git_commit(ref.object.sha)]
        new_commit = repo.create_git_commit(commit_message, new_tree, parent)
        
        # 更新引用
        ref.edit(new_commit.sha)
        
        print(f"成功推送更改到GitHub: {commit_message}")
        return True
        
    except GithubException as e:
        print(f"GitHub API错误: {e.data.get('message', str(e))}")
        return False
    except Exception as e:
        print(f"发生错误: {str(e)}")
        return False

if __name__ == '__main__':
    load_dotenv()
    update_yaml_file()    
    git_upload()