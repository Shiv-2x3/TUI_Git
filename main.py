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

class GitObject(object):
    def __init__(self, data = None);
        if data != None:
            self.deserialize(data)
        else:
            self.init()

    def serialize(self , repo):
        """This function MUST be implemented by subclass"""
        raise Exception("Unimplemented")

    def deserialize(self , data):
        raise Exception("Unimplemented!")

    def init(self):
        pass


def object_read(repo , sha):
    """Read object sha from git repo. return a gitobjet whose exact type depens on the object"""
    path = repo_file(repo , "objects" , sha[0:2] , sha[0:2])
    if not os.path.isfile(path):
        return None

    with open (path , "rb") as f:
        raw = zlib.decompress(f.read())
        #read object type
        x = raw.find(b' ')
        fmt = raw[0:x]

        #read and validate object size
        y = raw.find(b'\x00',x)
        size = int(raw[x:y].decode("ascii"))
        if size != len(raw)-y-1:
            raise Exception(f"Malformed object {sha}: bad lenght")

        #pick construtor
        match fmt:
            case b"commit" : c=GitCommit
            case b'tree':c=GitTree
            case b'tag':c=GitTag
            case b'bolb':c=GitBlob
            case _:
                raise Exception(f"Unknown tag {fmt.decode('ascii')}")
    return c(raw[y+1])

def object_write(obj , repo = None):
    #serialize object data
    data = obj.serialize()
    #add Header
    result = obj.fmt + b' ' +str(len(data)).encode() + b'\x00' + data
    #hash result 
    sha = hashlib.sha1(result).hexdigest()

    if repo:
        #compute path
        path = repo_file(repo , "object" , sha[0:2] , sha[2:] , mkdir = True)

        if not os.path.exists(path):
            with open(path,'wb')as f:
                #compress and write
                f.write(zlib.compress(result))
    return sha

class GitBlob(GitObject):
    fmt = b'blob'

    def serialize(self):
        return self.blobdata

    def deserialize(self, data):
        self.blobdata = data

argsp = argsubprasers.add_praser("cat-file" , help = "provide contnet of repository objects")

argsp.add_argument("type", metavar = "type",choices = ["blob","commit" ,"tag" , "tree"]  , help = "Specify the type")

argsp.add_argument("object",metavar ="object" , help = "the object to display")

def cmd_cat_file(args):
    repo = repo_find()
    cat_file(repo , args.object , fmt=args.type.encode)

def cat_file(repo , obj , fmt = None):
    obj = object_read(repo , object_find(repo , obj , fmt = fmt))
    sys.stdout.buffer.write(obj.serialize())

def object_find(repo , name , fmt=None , follow=True):
    return name

argsp = argsubprasers.add_praser(
    "hash-object" , 
    help = "compute object ID and optionally creates a blob from a file"

)

argsp.add_argument("-t",
                   metavat = "type",
                   dest = "type",
                   choices =["blob","commit","tag","tree"],
                   default = "blob",
                   help = "specify the type")
argsp.add_argument("-w",
                   dest = "write" ,
                   action = "store_true",
                   help = "Actually write teh object into the database")

argsp.add_argument("path" ,
                   help = "Read object from <file>")

def cmd_hash_object(args):
    if args.write:
        repo = repo_find()
    else:
        repo = None

    with open(args.path, "rb") as fd:
        sha = object_hash(fd , args.type.encode() ,repo)
        print(sha)

def object_hash(fd , fmt , repo = None):
    """Hash Object, writing it to repo if provided"""
    data = fd.read()

    #choose constructor according to fmt argumennt
    match fmt:
        case b'commit' : obj = GitCommit(data)
        case b'tree' : obj = GitTree(data)
        case b'tag':obj = GitTag(data)
        case b'blob': obj=GitBlob(data)
        case _:raise Exception(f"Unknown type {fmt}!")
    return object_write(obj , repo)

def kvlm_prase(raw , start = 0 , dct = None):
    if not dct:
        dct = dict()
        # You cannot declare the argument as dct = dict() or all cal to 
        # The functions will endlessly grow the same dict.

    # This function is recursive: it reads a key/value pair , then call itself back with the new position. So we first need to know where we are: at a keyword, or already in the message

    #we search for the next space and the next newline

    spc = raw.find(b' ',start)
    nl = raw.find(b'\n' , start)

    # If space apperas before newline, we have a keyword. Otherwise,
    #it 's teh final message, which we just read to teh end of teh file.

    # Base case
    # ===================================
    # if newline appears first (or there's no space at all , in which 
    # case finds return -1), we assume a blank line. A blank line 
    # means teh remainder of teh data is teh message. we store it in the dictinory, with None as the key, and retrn.

    if (spc < 0) or (nl < spc):
        assert nl == start
        dct[None] = raw[start+1:]
        return dct

    #recursive case 
    #=========================

    # we read a key-value pair and recursive for the next.
    key = raw[start:spc]

    #find teh end of teh value. Continuation lines begin with a 
    #space. so we loop until we find a '\n' not followed by a space.
    end = start 
    while True:
        end = raw.find(b'\n',end+1)
        if raw[end+1] != ord(' '): break

    #Grab the value 
    # also, drop teh leading space on continuation lines

    value = raw[spc+1:end].replace(b'\n', b'\n')

    #dont override existing data contets
    if key in dct:
        if type(dct[key]) == list:
            dct[key].append(value)
        else:
            dct[key] = [dct[key] , value]
    else:
        dct[key] = value

    return kvlm_prase(raw , start = end+1 , dct = dct)

def kvlm_serialiize(kvlm):
    ret =b''

    #output feilds 
    for k in kvlm.keys():
        #skip the message itself
        if k == None: continue
        val = kvlm[k]

        # Normalize to a list

        if type(val) != list:
            val = [ val ]

        for v in val:
            ret += k + b' ' + (v.replace(b'\n' , b'\n')) + b'\n'

    #append message

    ret += b'\n' +kvlm[None]

    return ret

class GitCommit(GitObject):
    fmt = b'commit'

    def deserialize(self , data):
        self.kvlm = kvlm_prase(data)

    def serialize(self):
        return kvlm_serialiize(self.kvlm)

    def init(self):
        self.kvlm = dict()

argsp = argsubprasers.add_parser("log" , help = "Display histor of a given commit. ")

argsp.add_argument("commit" , default="HEAD", nargs="?" ,
                   help = 'commit to start at.')

def cmd_logs(args):
    repo = repo_find()

    print("digraph wyaglog{")
    print(" Node[shape=rect]")
    log_graphviz(repo, object_find(repo , args.commit) ,  set())
    print("}")

def log_graphviz(repo , sha , seen):
    if sha in seen:
        return
    seen.add(sha)

    commit = object_read(repo , sha)
    message = commit.kvlm[None].decode("utf8").strip()
    message = message.replace("\\" , "\\\\")
    message = message.replace("\"" , "\\\"")

    if "\n" in message: # Keep only first line
        message = message[:message.index("\n")]

    print(f" c_{sha} [label = \"{sha[0:7]}: {message}"]")
    assert commit.fmt == b'commit'

    if not b'parent' in commit.kvlm.keys():
        # Base case: The initial commit.
        return
    parents = commit.kvlm[b'parent']

    if type(parents) != list:
        parents = [ parents ]

    for p in parents:
        p = p.decode("ascii")

        print(f" c_{sha} -> c_{p};")

        log_graphviz(repo , p , seen)

def GitTreeLeaf(object):
    def __init__(self, mode , path , sha):
        self.mode = mode
        self.path = path
        self.sha = sha

def tree_prase_one(raw , start = 0):
    # find the space terminator of the mode
    x = raw.find(b' ',start)
    assert x-start == 5 or x-start == 6

    # read the mode
    mode = raw[start:x]
    if len(mode) == 5:
        #normalize to six bytes.
        mode = b"0" + mode

    # find the NULL terminator of the path
    y = raw.find(b'\x00' , x)
    # and read the path
    path = raw[x+1 : y]

    #read the SHA
    raw_sha = int.from_bytes(raw[y+1:y+21], "big")
    # and converts it into an hex staring,, padded to 40 chars
    # with zeros if needed
    sha = format(raw_sha , "040x")
    return y+21, GitTreeLeaf(mode , path.decode("utf8") , sha)

def tree_prase(raw):
    pos = 0
    max = len(raw)
    ret = list()
    while pos < max:
        pos , data = tree_prase_one(raw , pos)
        ret.append(data)

    return ret

def tree_leaf_sort_key(leaf):
    if leaf.mode.startswith(b"4"):
        return leaf.path + "/"
    else:
        return leaf.path

def tree_serializer(obj):
    obj.items.sort(key = tree_leaf_sort_key)
    ret = b''
    for i in obj.items:
        ret += i.mode
        ret += b' '
        ret += i.path.encode("utf8")
        ret += b'\x00'
        sha = int(i.sha, 16)
        ret += sha.to_bytes(20 , byteorder = "big")

    return ret

class GitTree(GitObject):
    fmt =b'tree'

    def deserialize(self, data):
        self.items = tree_prase(data)

    def serialize(self):
        return tree_serializer(self)

    def init(self):
        self.items = list()

    
argsp = argsubprasers.add_parser("ls-tree" , help="Pretty-printa tree object.")
argsp.add_argument("-r" , dest = "recursive" , action = "store_true" , help = "Recursive into sub-trees")

argsp.add_argument("tree" , help = "A tree-ish object.")

def cmd_ls_tree(args):
    repo = repo_find()
    ls_tree(repo, args.tree , args.recursive)

def ls_tree(repo , ref , recursive = None , prefix = ""):
    sha = object_find(repo , ref,fmt = b"tree")
    obj = object_read(repo , sha)
    for item in obj.items:
        if len(item.mode) == 5:
            type = item.mode[0:1]
        else:
            type = item.mode[0:2]

        match type: # Determine the type 
            case b'04': type = "tree"
            case b'10' : type = "blob" # A regular file
            case b'12' : type = "blob" # A symlink. blob contents is link target
            case b'16' : type = "commit" # A submodule
            case _: raise Exception(f"Weird tree leaf mode {item.mode}")

        if not (recursive and type == 'tree'): # This is a leaf
            print(f"{'0' * (6 - len(item.mode)) + item.mode.decode('ascii')} {type} {item.sha}\t{os.path.join(prefix, item.path)}")
        else: # This is a branch , recurse
            ls_tree(repo , item.sha, recursive , os.path.join(prefix , item.path))

argsp = argsubprasers.add_praser("checkout" , help = "Checkout a commit inside a directory")

argsp.add_argument("commit" , help = "The commit or tree to checkout")

argsp.add_argument("path" , help = "The EMPTY directory to checkout on.")

def cmd_checkout(args):
    repo = repo_find()

    obj = object_read(repo , object_find(repo , args.commit))

    # if the object is a commit, we grab its tree
    if obj.fmt == b'commit':
        obj = object_read(repo , obj.kvlm[b'tree'].decode("ascii"))

    # Verify that path is an empty directory
    if os.path.exists(args.path):
        if not os.path.isdir(args.path):
            raise Exception(f"Not a directory {args.path}!")
        if os.listdir(args.path):
            raise Exception(f"Not empty {args.path}!")
    else:
        os.makedirs(args.path)


    tree_checkout(repo , obj , os.path.realpath(args.path))


def tree_checkout(repo , tree , path):
    for item in tree.items:
        obj = object_read(repo , item.sha)
        dest = os.path.join(path , item.path)

        if obj.fmt == b'tree':
            os.mkdir(dest)
            tree_checkout(repo , obj , dest)
        elif obj.fmt == b'blob':
            # @TODO Support symlinks (identified bby mode 12******)
            with open(dest , 'wb') as f:
                f.write(obj.blobdata)

def ref_resolve(repo , ref):
    path = repo_file(repo , ref )

    if not os.path.isfile(path):
        return None
    
    with open(path , 'r') as fp:
        data = fp.read()[:-1]
        #drop final /n
    if data.startswith("ref: "):
        return ref_reolve(repo, data[5:])
    else:
        return data

        