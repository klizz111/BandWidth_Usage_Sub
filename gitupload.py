import os
from datetime import datetime
from git import Repo, GitCommandError
from ruamel.yaml import YAML
from xml.etree import ElementTree as ET

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

        # 写入文件
    with open('/tmp/vnstat_subscribe_tmp', 'w') as f:
        f.write(str(total))

        if current_day == 1:
            yesterday = 0
        else:
            with open('/tmp/vnstattmp', 'r') as f:
                yesterday = float(f.read())
    today = total - yesterday

    return total, today

def update_yaml_file():
    # 解析yaml文件
    yaml = YAML()
    with open('config.yaml', 'r') as f:
        config = yaml.load(f)

    # 更新yaml文件
    total, today = get_bandwidth_usage()
    config['proxies'][0]['name'] = str(datetime.now().month) + '月流量: ' +  str(total) + ' GB'
    config['proxies'][1]['name'] = str(datetime.now().month) + '昨日使用流量: ' +  str(today) + ' GB'

    # 写入yaml文件
    with open('config.yaml', 'w') as f:
        yaml.dump(config, f)

def git_upload(commit_message=None):
    """
    将当前目录的更改推送到远程Git仓库
    
    参数:
        commit_message: 自定义提交信息，默认为"update subscription"
    """
    try:
        from git import Repo, GitCommandError
        import os
        
        # 设置默认提交信息
        if commit_message is None:
            commit_message = f"update subscription - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        # 创建或打开仓库对象
        repo_path = os.path.abspath('.')
        print(f"操作仓库路径: {repo_path}")
        
        try:
            repo = Repo(repo_path)
        except Exception as e:
            print(f"不是有效的Git仓库，尝试初始化: {str(e)}")
            repo = Repo.init(repo_path)
            
        # 检查是否有远程仓库
        if len(repo.remotes) == 0:
            print("警告: 没有配置远程仓库，只能进行本地提交")
            has_remote = False
        else:
            has_remote = True
            
        # 添加文件到暂存区
        repo.git.add(all=True)
        
        # 检查是否有更改需要提交
        if repo.is_dirty() or len(repo.untracked_files) > 0:
            # 提交更改
            repo.git.commit('-m', commit_message)
            print(f"已提交更改: {commit_message}")
            
            # 如果有远程仓库，推送更改
            if has_remote:
                print("正在推送到远程仓库...")
                repo.git.push()
                print("成功推送到远程仓库")
        else:
            print("没有需要提交的更改")
            
        return True
    except GitCommandError as git_error:
        print(f"Git操作失败: {str(git_error)}")
        return False
    except Exception as e:
        print(f"发生错误: {str(e)}")
        return False

if __name__ == '__main__':
    git_upload()