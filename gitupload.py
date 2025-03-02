import os
from datetime import datetime
from ruamel.yaml import YAML
from xml.etree import ElementTree as ET
from dotenv import load_dotenv
import subprocess

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
        if not os.path.exists('/tmp/vnstat_subscribe_tmp'):
            with open('/tmp/vnstat_subscribe_tmp', 'w') as f:
                f.write('0')

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

def get_changed_files():
    """获取已修改和新增的文件列表"""
    # 将所有新文件添加到跟踪中
    subprocess.run(['git', 'add', '-A'], stdout=subprocess.PIPE)
    
    # 获取已更改的文件
    result = subprocess.run(['git', 'diff', '--name-only', '--cached'], stdout=subprocess.PIPE)
    files = result.stdout.decode('utf-8').split('\n')
    return [f for f in files if f and not f.startswith('.') and f != '.env']

def git_upload(commit_message=None):
    """
    使用PyGithub将当前目录的更改推送到远程GitHub仓库
    
    参数:
        commit_message: 自定义提交信息，默认为"update subscription"
    """
    try:
        from github import Github, GithubException, Auth, InputGitTreeElement
        import os
        from datetime import datetime
        
        # 加载认证信息
        access_token = os.getenv('GITHUB_TOKEN')
        username = os.getenv('GITHUB_USERNAME')
        repo_name = os.getenv('GITHUB_REPO')  # 仓库名称
        
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
        print(repo)

        # 获取默认分支
        default_branch = repo.default_branch
        ref = repo.get_git_ref(f'heads/{default_branch}')
        
        # 获取当前commit
        current_commit = repo.get_commit(ref.object.sha)
        base_tree = current_commit.commit.tree
        print(f"当前commit: {current_commit}")
        
        # 准备文件更新列表
        element_list = []
        
        # 获取已修改的文件列表
        changed_files = get_changed_files()
        print(f"需要提交的文件: {changed_files}")
        
        for file_path in changed_files:
            try:
                with open(file_path, 'rb') as f:
                    content = f.read()

                try:
                    content_str = content.decode('utf-8')
                    # 创建blob
                    blob = repo.create_git_blob(content_str, 'utf-8')
                except UnicodeDecodeError:
                    print(f"文件 {file_path} 为二进制文件，使用base64编码提交")
                    import base64
                    blob = repo.create_git_blob(base64.b64encode(content).decode('ascii'), 'base64')
                
                # 使用InputGitTreeElement对象
                element = InputGitTreeElement(
                    path=file_path,
                    mode='100644',
                    type='blob',
                    sha=blob.sha
                )
                element_list.append(element)
            except Exception as e:
                print(f"处理文件 {file_path} 时出错: {str(e)}")
        
        if not element_list:
            print("没有文件需要提交")
            return True
            
        # 创建新的tree
        try:
            new_tree = repo.create_git_tree(element_list, base_tree)
            
            # 创建新的commit
            parent = [repo.get_git_commit(ref.object.sha)]
            new_commit = repo.create_git_commit(commit_message, new_tree, parent)
            
            # 更新引用
            ref.edit(new_commit.sha)
            
            print(f"成功推送更改到GitHub: {commit_message}")
            return True
        except Exception as e:
            print(f"创建Git树时出错: {str(e)}")
            return False
        
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