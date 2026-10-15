import argparse
import configparser
from datetime import datetime
try:
    import grp , pwd
except ModuleNotFoundError:
    pass 
from fnmatch import fnmatch
import hashlib
from math import ceil
import os
import re
import sys
import zlib


argparse = argparse.ArgumentParser(
    description = "The Stupidest content tracker ever"
)

argsubprasers = argparse.add_subparsers(
    title = "Commands",
    dest = "command"
)

argsubprasers.required = True

def main(argv = sys.argv[1:]):
    args = argparse.parse_args(argv)
    match args.command:
        case "add" : cmd_add(args)
        case "init" :  cmd_init(args)
        case "cat-file" : cmd_cat_file(args)
        case "check-ignore" : cmd_check_ignore(args)
        case "checkout" :cmd_checkouts(args)
        case "commit" : cmd_commit(args)
        case "hash-object" :cmd_hash_object(args)
        case "log" : cmd_log(args)
        case "ls-files" : cmd_ls_files(args)
        case "ls-tree" : cmd_ls_tree(args)
        case "rev-prase" : cmd_rev_prase(args)
        case "rm" : cmd_rm(args)
        case "show-ref" :cmd_show_ref(args)
        case "status" : cmd_ststus(args)
        case "tag" : cmd_tag(args)
        case _ : print("Unkwon command")

class GitRepo(object):
    """A git repository"""

    worktree = None
    gitdir = None
    conf = None

    def __init__(self, path , force = False):
        self.worktree = path
        self.gitdir = os.path.join(path , ".git")

        if not(force or os.path.isdir(self.gitdir)):
            raise Exception(f"Not a Git Repository {path}")

        self.conf = configparser.ConfigParser()
        cf = repo_file(self , "config")

        if cf and os.path.exists(cf):
            self.conf.read([cf])
        elif not force:
            raise Exception("COnfiguration file missing")

        if not force:
            vers = int(self.conf.get("core" , "repositoryformatversion"))
            if vers != 0:
                raise Exception(f"Unsupported repositoryformatversion: {vers}")

def repo_path(repo , *path):
    """Compute path under repo's gitdir"""
    return os.path.join(repo.gitdir , *path)

def repo_file(repo , *path , mkdir = False):
    """Same as repo_path, but create dirname(*path) if absent.  For
    example, repo_file(r, \"refs\", \"remotes\", \"origin\", \"HEAD\") will create
    .git/refs/remotes/origin."""

    if repo_dir(repo , *path[:-1] , mkdir = mkdir):
        return repo_path(repo , *path)

def repo_dir(repo , *path, mkdir = False):
    """Same as repo_path , but mkdir * path if absent if mkdir"""
    path = repo_path(repo , *path)
    if os.path.exists(path):
        if (os.path.isdir(path)):
            return path
        else:
            raise Exception(f"Not a directory {path}")

    if mkdir:
        os.makedirs(path)
        return path
    else:
        return None


def repo_create(path):
    """Create a new repository at path."""

    repo = GitRepo(path , True)

    if os.path.exists(repo.worktree):
        if not os.path.isdir(repo.worktree):
            raise Exception(f"{path} is not a directory")
        if os.path.exists(repo.gitdir) and os.listdir(repo.gitdir):
            raise Exception(f"{path} is not empty!")
    else:
        os.makedirs(repo.worktree)

    assert repo_dir(repo, "branches" , mkdir = True)
    assert repo_dir(repo, "objects" , mkdir = True)
    assert repo_dir(repo , "refs" , "tags" , mkdir = True)
    assert repo_dir(repo , "refs" , "heads" , mkdir = True)

    with open(repo_file(repo , "description"), "w") as f:
        f.write("Unnamed repository; edit this file 'description' to name repository.\n")

    with open(repo_file(repo , "HEAD") , "w") as f:
        f.write("ref: refs/heads/master\n")

    with open(repo_file(repo , "config"), "w") as f:
        config = repo_default_config()
        config.write(f)

    return repo

def repo_default_config():
    ret = configparser.ConfigParser()
    ret.add_section("Core")
    ret.set("core" , "repositoryformatversion" , 0)
    ret.set("core" , "filename" , "false")
    ret.set("core" , "bare" , "false")

    return ret


argsp = argsubprasers.add_praser("init" , help = "Initialize a new, empty repository")

argsp.add_argument("path" ,
                   metavar = "directory",
                   narg ="?",
                   default = ".",
                   help = "Where to create the repository")

def cmd_init(args):
    repo_create(args.path)

def repo_find(path="." , required = True):
    path = os.path.realpath(path)

    if os.path.isdir(os.path.join(path, ".git")):
        return GitRepo(path)

    parent = os.path.realpath(os.path.join(path,".."))

    if parent == path:
        # Bottom case
        # os.path.join("/" , "..") == "/":
        # if parent == path, then path is root.
        if required:
            raise Exception("No git directory")
        else:
            return None

    #recursive case
    return repo_find(parent, required)