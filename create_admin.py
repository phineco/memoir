"""生产环境初始化：创建管理员账号（可选建家庭）。

seed.py 会清空所有表，仅用于原型演示；生产部署用这个脚本。

示例：
  python create_admin.py --phone 13800000000 --nickname 主持人 --family-name 王家
  （密码交互输入，不在命令行留痕）
"""
import argparse
import datetime
import getpass

from werkzeug.security import generate_password_hash

from config import Config
from models import Family, FamilyMember, User, get_session, init_db, new_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phone", required=True, help="手机号（登录用）")
    ap.add_argument("--nickname", default="", help="昵称")
    ap.add_argument("--family-name", default="", help="同时创建一个家庭（可选）")
    ap.add_argument("--family-id", default="", help="家庭 id（可选，默认随机）")
    args = ap.parse_args()

    init_db(Config.DATABASE_URL)
    s = get_session()

    if s.query(User).filter_by(phone=args.phone, del_flag=0).first():
        print(f"手机号 {args.phone} 已存在，跳过创建")
        return

    password = getpass.getpass("设置登录密码：").strip()
    if len(password) < 6:
        print("密码至少 6 位")
        return

    u = User(id=new_id(), phone=args.phone, nickname=args.nickname or args.phone,
             password_hash=generate_password_hash(password),
             create_date=datetime.datetime.now())
    s.add(u)
    s.flush()

    if args.family_name:
        fid = args.family_id or new_id()[:8]
        if s.query(Family).filter_by(id=fid, del_flag=0).first():
            print(f"家庭 id {fid} 已存在")
            return
        fam = Family(id=fid, name=args.family_name, owner_user_id=u.id,
                     create_by=u.id, create_date=datetime.datetime.now())
        s.add(fam)
        s.add(FamilyMember(id=new_id(), family_id=fid, user_id=u.id, role="owner",
                           create_by=u.id, create_date=datetime.datetime.now()))
        print(f"家庭「{args.family_name}」(id={fid}) 已创建，你是创建者")
    s.commit()
    print(f"用户 {args.phone} 创建成功")


if __name__ == "__main__":
    main()
