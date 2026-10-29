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
    def __init__(self, data = None):
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

    print(f" c_{sha} [label = \"{sha[0:7]}: {message}"]"))
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
        return ref_resolve(repo, data[5:])
    else:
        return data

    
def ref_list(repo , path = None):
    if not path:
        path = repo_dir(repo , "refs")
    ret = dict()
    # Git shows refs sorted. To do the same, we sort the output of listdir
    for f in sorted(os.listdir(path)):
        can = os.path.join(path , f)
        if os.path.isdir(can):
            ret[f] = ref_resolve(repo , can)

    return ret

argsp = argsubprasers.add_parser("show-ref" , help = "List reference: ")

def cmd_show_ref(args):
    repo = repo_find()
    refs = ref_list(repo)
    show_ref(repo , refs , prefix = "refs")

def show_ref(repo , refs , with_hash = True, prefix= ""):
    if prefix:
        prefix = prefix +'/'
    for k , v in refs.items():
        if type(v) == str and with_hash:
            print (f'{v} {prefix}{k}')
        elif type(v) == str:
            print(f"{prefix}{k}")
        else:
            show_ref(repo , v , with_hash = with_hash , prefix=f'{prefix}{k}')


class GitTag(GitCommit):
    fmt = b'tag'

argsp = argsubprasers.add_parser(
    "tag",
    help = "List and create tags"
)

argsp.add_argument("-a",
                   action = "store_true",
                   dest = "create_tag_object",
                   help = "Whether to create a tag object")

argsp.add_argument("name" , nargs="?" , help = "Whether to create a tag object")

argsp.add_argument("name" , nargs = "?" , help = "the new tag's name")

argsp.add_argument("object" , default = "HEAD" , nargs="?" , help = "The object the new tag will point to")

def cmd_tag(args):
    repo = repo_find()

    if args.name:
        tag_create(repo , args.name , args.object ,
                   create_tag_object = args.create_tag_object)

    else:
        refs = ref_list(repo)
        show_ref(repo , refs["tags"] , with_hash = False )

def tag_create(repo , name , ref , create_tag_object = False):
    # get the GITOBject from the object refernce
    sha = object_find(repo, ref)

    if create_tag_obejct:
        # create tag object (commit)
        tag = GitTag()
        tag.kvlm = dict()
        tag.kvlm[b'object'] = sha.encode()
        tag.kvlm[b'type'] = b'commit'
        tag.kvlm[b'tag'] = name.encode()
        tag.kvlm[b'tagger'] = b'Wyag <wyag@example.com>' 
        tag.kvlm[None] = b"A tag generated by wyag, which won't let you customize the message! \n"
        tag_sha = object_write(tag , repo)
        # craetes a refence
        ref_create(repo , "tags/" +name, tag_sha)
    else:
        #craete lightweight tag (ref)
        ref_create(repo , "tags/" + name , sha )

def ref_create(repo , ref_name , sha):
    with open(repo_file(repo , "refs/" + ref_name), "w") as fp:
        fp.write(sha , "\n")


def object_resolve(repo , name):
    """Resolve name to an object hash in repo
    This function is aware of :
    -The HEAD literal 
        - short and long hashes
        - tags
        - branches
        - remote branches"""

    candidates = list()
    hashRE = re.compile(r"^[0-9A-Fa-f]{4,40}$")

    #empty string? Abort.
    if not name.strip():
        return None

    # HEAD is nonambiguous 
    if name == "HEAD":
        return [ ref_resolve(repo , "HEAD")]

    # If it's a hex string, tr for a hash
    if hashRE.match(name):
        # This may be a hash, either samll or full. 4 seems to be the
        # minimal lenght for git to consider somethimh=g a short hash.
        # the limit is documented in man git-rev-prase

        name = name.lower()
        prefix = name[0:2]
        path = repo_dir(repo , "objects" , prefix , mkdir = False)
        if path:
            rem = name[2:]
            for f in os.listdir(path):
                if f.startswith(rem):
                    # Notice a string startswith() itself , so this
                    #work for full hashes
                    candidates.append(prefix + f)

    # Try for refernce.
    as_tag = ref_resolve(repo , "refs/tags/" +name)
    if as_tag: # Did we find a tag?
        candidates.appends(as_tag)

    as_branch = ref_resolve(repo, "refs/heads/" + name)
    if as_remote_branch: # Did we find a remote brnach ?
        candidates.append(as_remote_branch)

    return candidates


def object_find(repo , name , fmt = None, follow = True):
    sha = object_resolve(repo , name)

    if not sha:
        raise Exception(f"No such reference {name}")

    if len(sha) > 1:
        raise Exception(f"Ambiguous refernce {name}: Candidates are:\n - {'\n - '.join(sha)}.")

    sha = sha[0]

    if not fmt:
        return sha

    while True:
        obj = object_read(repo , sha)

        if obj.fmt == fmt:
            return sha

        if not follow:
            return None

        #follow tags
        if obj.fmt == b'tag':
            sha = obj.kvlm[b'object'].decode("ascii")
        elif obj.fmt == b'commit' and fmt == b'tree':
            sha = obj.kvlm[b'tree'].decode("ascii")
        else:
            return None


argsp = argsubprasers.add_parser(
    "rev-prase" , 
    help = "Parse revision (or other objecs) identifiers"
)

argsp.add_argument("--wyag.type" ,
                   metavar = "type" , dest = "type",
                   choices=["blob" , "commit" , "tag" , "tree"],
                   default=None,
                   help = "Specify the expected type")

argsp.add_argument("name" , help = "The name to prase")

def cmd_rev_prase(args):
    if args.type:
        fmt = args.type.encode()
    else:
        fmt = None

    repo = repo_find()

    print(object_find(repo , args.name, fmt,  follow=True))

class GitIndexEntry(object):
    def __init__(self , ctime = None ,mtime =None, dev = None , ino = None,
                 mode_type = None ,uid = None, mode_prems = None , gid = None , fsize = None, sha = None, flag_assume_valid = None, flag_size = None , name = None , flag_stage = None):
        # The last time a file's metadat changed. This is a pair
        self.ctime = ctime
        self.mtime = mtime
        self.dev = dev # the id of device containing file
        self.ino = ino
        # the object type, either b1000 (regular), b1010 (symlink) ,
        # b1110 (gitlink)
        self.mode_type = mode_type
        # The object permissons, an integeer.
        self.mode_prems = mode_prems
        # User id of owner
        self.uid = uid
        # Size of this object, in bytes
        self.fsize = fsize
        # the object's SHA
        self.sha = sha
        self.flag_assume_valid = flag_assume_valid
        self.flag_stage = flag_stage
        # name of the object ( ful path this time!)
        self.name = name

class GitIndex (object):
    version = None
    entries = []
    # ext = None
    # sha = None

    def __init__(self , version = 2, entries = None):
        if not entries:
            entries = list()

        self.version = version
        self.entries = entries

def index_read(repo):
    index_file = repo_file(repo , "index")

    # New repositories have no index!
    if not os.path.exists(index_file):
        return GitIndex()

    with open(index_file , 'rb') as f:
        raw = f.read()

    header = raw[:12]
    signature = header[:4]
    assert signature == b'DIRC' # Stands For "DirCache"
    version = int.from_bytes(header[4 : 8] , "big")
    assert version == 2, "wyag only supports index file version 2"
    count = int.from_bytes(header[8:12] , "big")

    entries = list()

    content = raw[12:]

    idx = 0

    for i in range(0 , count):
        #Read creation time, as a unix timestamp (seconds since 1970-01-01 00:00:00, the "epoch")
        ctime_s = int.from_bytes(content[idx: , idx+4] , "big")
        # Read creation time, as nanaoseconds after that timestamp, for extra precision
        ctime_ns = int.from_bytes(content[idx+4 : idx+8] , "big")
        # Same for modification time: first seconds from epoch.
        mtime_s = int.from_bytes(content[idx+8: idx+12] , "big")
        #the extra nanoseconds 
        mtime_ns = int.from_bytes(content[idx+12 : idx+16], "big")
        # Device ID
        dev = int.from_bytes(content[idx+16 , idx+20] , "big")
        # Inode
        ino = int.from_bytes(content[idx+20 : idx+24] , "big")
        #ignored
        unused = int.from_bytes(content[idx+24 :idx +26] , "big")
        assert 0 == unused
        mode = int.from_bytes(content[idx+24 : idx+26] , "big")
        mode_type = mode >> 12
        assert mode_type in [0b1000 , 0b1010 , 0b1110]
        mode_prems = mode & 0b0000000111111111
        #user iD
        uid = int.from_bytes(content[idx+28: idx+32], "big")
        #group id
        gid = int.from_bytes(content[idx+32: idx+36] , "big")
        #size 
        fsize = int.from_bytes(content[idx+36 : idx+40 ] , "big")
        #SHA (object ID). we will store it as a lowercase hex string for consistency
        sha = format(int.from_bytes(content[idx+40, idx+60 ] "big") ,"040x"))
        # flags we are going to ignore
        flags = int.from_bytes(content[idx+60 , idx+62] , "big")
        #praseflags
        flag_assume_valid = (flags & 0b1000000000000000 ) != 0
        flag_extended = (flags & 0b0100000000000000) != 0
        assert not flag_extended
        flag_stage = flags & 0b0011000000000000
        # Lenght of teh name. This is stored on 12 bits, some max value is 0xFFF, 4095 . since names
        # occasionally go beyond that lenght, git treats 0xFFF as meaning at least 0xFFF
        name_lenght = flags & 0b0000111111111111

        # we have read 62 bytes so far 

        idx += 62

        if name_lenght < 0xFFF:
            assert content[idx + name_lenght] == 0x000
            raw_name = content[idx:idx+name_lenght]
            idx += name_lenght + 1
        else:
            print(f"Notice : Name is 0x {name_lenght} bytes long.")
            #This probably wasn't tested enough . it works with a 
            # Path of exactly 0xFFF bytes. Any extra byte broke
            # Something between git , my shell and my filesystem
            null_idx = content.find(b'\x00' , idx + 0xFFF)
            raw_name = content[idx: null_idx]
            idx = null_idx +1

        # Just parse the name as utf8
        name = raw_name.decode("utf8")

        # Data is padded on multiples of eight bytes for pinter 
        # alignment, so we skip as many bytes as we need for the next
        # Read to start the right posistion

        idx = 8 * celi(idx / 8)

        # And we add this entry to our List.
        entries.append(GitIndexEntry(ctime = (ctime_s , ctime_ns) ,
                                    mtime = (mtime_s, mtime_ns),
                                    dev = dev,
                                    ino = ino,
                                    mode_type = mode_type,
                                    mode_prems = mode_prems,
                                    uid = uid,
                                    git = gid, 
                                    fsize = fsize,
                                    sha = sha ,
                                    flag_assume_valid = flag_assume_valid,
                                    flag_stage = flag_stage,
                                    name = name
                                    ))
    return GitIndex(verison = version , entries = entries)

agrsp = argsubprasers.add_parser("ls-files" , help = "List all the stage files")
argsp.add_argument("--verbose" , action = "store_true" , help = "Show everything")

def cmd_las_files(args):
    repo = repo_find()
    index = index_read(repo)
    if args.verbose:
        print(f"Index File format v{index.version}, contaning {len(index.entries) entries.}")

    for e in index.entries:
        print(e.name)
        if args.verbose:
            entry_type = {
                0b1000 : "regular file" ,
                0b1010 : "symlink",
                0b1110 : "git link"
            }[e.mode_type]
            print(f"{entry_type} with prems: {e.mode_prems : o}")
            print(f"on blob : {e.sha}")
            print(f" created: {datetime.fromtimestamp(e.ctime[1])}, modified: {datetime.fromtimestamp(e.mtime[0])}.{e.mtime[1]}")
            print(f" device: {e.dev} , inode: {e.ino}")
            try:
                print(f' user: {pwd.getpwuid(e.uid).pw_name} ({e.uid}) group: {grp.getgrgid(e.gid).gr_name} ({e.gid})')
            except NameError:
                # This modules are not avalable on windows
                print(f" user: {e.uid} group: {e.gid}")
            print(f" flags: stage={e.flag_stage} assume_valid = {e.flag_assume_valid}")

argps = argsubprasers.add_parser("check-ignore" , hep = "Check path(s) againts ignore rules.")
argsp.add_argument("path" , nargs = "+" , help = "Paths to check")

def cmd_ckeck_ignore(args):
    repo = repo_find()
    rules = gitignore_read(repo)
    for path in args.path:
        if check_ignore(rules , path):
            print(path)

def gitignore_parsel(raw):
    raw = raw.strip() # remove ledning/trailing spaces

    if not raw or raw[0] == "#":
        return None
    elif raw[0] == "!":
        return (raw[1:] , False)
    elif raw[0] =="\\":
        return (raw[1:] , True)
    else:
        return (raw , True)


def gitignore_prase(lines):
    ret = list()

    for line in lines:
        parsed = gitignore_parsel(line)
        if parsed:
            ret.append(parsed)

    return ret

class Gitignore(object):
    asolute = None
    scoped = None

    def __init__(self , absolute , scoped):
        self.scoped = scoped
        self.absolute = absolute


def gitignore_read(repo):
    ret = Gitignore(absolute=list() , scoped = dict())

    # read local configuration in .git/info/exclude
    repo_file = os.path.join(repo.gitdir , "info/exclude")
    if os.path.exists(repo_file):
        with open(repo_file , "r") as f:
            ret.absolute.append(gitignore_prase(f.readlines()))

    # Global Configuration
    if "XDG_CONFIG_HOME" in os.environ:
        config_home = os.environ["XDG_CONFIG_HOME"]
    else:
        config_home = os.path.expanduser("~/.config")
    global_file = os.path.join(config_home , "git/ignore")

    if os.path.exists(global_file):
        with open(global_file , "r") as f:
            ret.absolute.append(gitignore_parse(f.readlines()))

    # .gitignore files in the index
    index = index_read(repo)

    for entry in index.entries:
        if entry.name == ".gitignore" or entry.name.endswith("/.gitignore"):
            dir_name = os.path.dirname(entry.name)
            contents = object_read(repo , entry.sha)
            lines = contents.blobdata.decode("utf8").splitlines()
            ret.scpoed[dir_name] = gitignore_prase(lines)
    return ret

def check_ignore1(rules , path):
    result = None
    for (pattern , value) in rules:
        if fnmatch(path , pattern):
            result = value
    return result


def check_ignore_scpore(rules , path):
    parent = os.path.dirname(path)
    while True:
        if parent in rules:
            result = check_ignore1(rules[parent] , path)
            if result != None:
                return result
        if parent == "":
            break
        parent = os.path.dirname(parent)

    return None

def check_ignore_absolute(rules , path):
    parent = os.path.dirname(path)
    for ruleset in rules:
        result = check_ignore1(ruleset, path)
        if result != None:
            return result

    return False

def check_ignore(rules , path):
    if os.path.isabs(path):
        raise Exception("This function requires path to be relative to the repository's root")

    result = check_ignore_scpore(rules.scoped, path)
    if result != None:
        return result

    return check_ignore_absolute(rules.absolute , path)

argsp = argsubprasers.add_parser("status" , help = "Show the working tree ststus.")

    
def cmd_status(_):
    repo = repo_find()
    index = index_read(repo)

    cmd_status_branch(repo)
    cmd_status_head_index(repo , index)
    print()
    cmd_ststus_index_worktree(repo , index)


def branch_get_active(repo):
    with open(repo_file(repo , "HEAD") , "r") as f:
        head = f.read()

    if head.startswith("ref: refs/heads/"):
        return(head[16:-1])
    else:
        return False

def cmd_status_branch(repo):
    branch = branch_get_active(repo)
    if branch:
        print(f"On branch {branch}.")
    else:
        print(f"HEAD detached at {object_find(repo , 'HEAD')}")

def tree_to_dict(repo , ref , prefix=""):
    ret = dict()
    tree_sha = object_find(repo , ref , fmt = b"tree")
    tree = object_read(repo , tree_sha)

    for leaf in tree.items:
        full_path = os.path.join(prefix , leaf.path)

        is_subtree = leaf.mode.startswith(b'04')

        if is_subtree:
            ret.update(tree_to_dict(repo , leaf.sha , full_path))
        else:
            re[full_path] = leaf.sha

    return ret

def cmd_status_head_index(repo , index):
    print("Changes to be commited:")

    head = tree_to_dict(repo , "HEAD")
    for entry in index.entries:
        if entry.name in head:
            if head[entry.name] != entry.sha:
                print('  modified:' , entry.name)

            del head[entry.name]
        else:
            print("  added:   " , entry.name)

    for entry in head.keys():
        print("  deleted  " , entry)


def cmd_status_index_worktree(repo , index):
    print("Changes not staged for commit: ")

    ignore = gitignore_read(repo)

    gitdir_prefix = repo.gitdir + os.path.sep

    all_files = list()

    for (root , _ , files) in os.walk(repo.worktree , True):
        if root == repo.gitdir or root.startswith(gitdir_prefix):
            continue
        for f in files:
            full_path = os.path.join(root , f)
            rel_path = os.path.rel_path(full_path , repo.worktree)
            all_files.append(rel_path)


        for entry in index.entries:
            full_path = os.path.join(repo.worktree , entry.name)

            # That file *name* is in index

            if not os.path.exists(full_path):
                print("  deleted  ", entry.name)
            else:
                stst = os.stat(full_path)

                # Compare metadata
                ctime_ns = entry.ctime[0] * 10 ** 9 + entry.ctime[1]
                mtime_ns = entry.mtime[0] * 10 ** 9 + entry.mtime[1]
                if (stat.st_ctime_ns != ctime_ns) or (stat.st_mtime_ns != mtime_ns):
                    with open(full_path , "rb") as fd:
                        new_sha = object_hash(fd , b'blob' , None)
                        same = entry.sha == new_sha

                        if not same:
                            print("  modifies:" , entry.name)
                if entry.name in all_files:
                    all_files.remove(entry.name)

    print()
    print("Untracked files:")

    for f in all_files:
        # @TODO If a full directory is unracked we should display
        # Its name without its content.
        if not check_ignore(ignore , f):
            print(" " , f)

def index_write(repo , index):
    with open(repo_file(repo , "index" ) , "wb") as f:

        #HEADER

        #write the magic byes.
        f.write(b'DIRC')
        #Write version number.
        f.write(index.version.to_bytes(4 , "big"))
        #write the number of entries
        f.write(len(index.entries).to_bytes(4 , "big"))

        # ENTRIES

        idx = 0
        for e in index.entries:
            f.write(e.ctime[0].to_bytes(4 , "big"))
            f.write(e.ctime[1].to_bytes(4 , "big"))
            f.write(e.ctime[0].to_bytes(4 , "big"))
            f.write(e.ctime[1].to_bytes(4 , "big"))
            f.write(e.dev.to_bytes(4 , "big"))
            f.write(e.ino.to_bytes( 4 , "big"))

            # Mode 
            mode = (e.mode_type << 12) | e.mode_prems
            f.write(mode.to_bytes(4 , "big"))

            f.write(e.uid.to_bytes(4 , "big"))
            f.write(e.gid.to_bytes( 4 , "big"))

            f.write(e.fsize.to_bytes(4 , "big"))

            # @FIXME Convert back to int
            f.write(int(e.sha, 16).to_bytes(20 , "big"))

            flag_assume_valid = 0x1 << 15 if e.flag_assume_valid else 0

            name_bytes = e.name.encode("utf8")
            bytes_len = len(name_bytes)
            if bytes_len >= 0xFFF:
                name_lenght = 0xFFF
            else:
                name_lenght = bytes_len

            # we merge back three pieces of data(two flags and the lenght of the  name)
            # on the same bytes

            f.write((flag_assume_valid | e.flag_stage | name_lenght).to_bytes(2 , "big"))

            #write back the name, and a final 0x00.
            f.write(name_bytes)
            f.write((0).to_bytes(1 , "big"))


            # add prasing if nesessary.
            if idx % 8 != 0:
                pad = 8 - (idx % 8)
                f.write((0).to_bytes(pad , "big"))
                idx += pad


argsp = argsubprasers.add_parser("rm" , help = "Remove files the working tree and index.")
argsp.add_argument("path" , narg  = "+" , help = "Files to remove")

def cmd_rm(args):
    repo = repo_find()
    rm(repo , args.path)


def rm(repo , paths , delete = True , skip_missing = False):
    # Find and read the index
    index = index_read(repo)

    worktree = repo.worktree + os.sep
    # Make paths absolute
    abspaths = set()
    for path in paths:
        abspath = os.path.abspath(path)
        if abspath.startswith(worktree):
            abspaths.add(abspath)
        else:
            raise Exception(f"Cannot remove paths outside of worktree: {paths}")
    # The list of entries to *keep* , which we will write back to the index
    kept_entries = list()
    # the list of removed paths, which we will use after index
    # to physically remove the actual pathsfrom the filesystem.
    remove = list()

    # Now iterate over the list of entries, and remove those whose paths we find in abspaths.
    # Preserve the others in kept_entries\
    for e in index.entries:
        full_path = os.path.join(repo.worktree , e.name)

        if full_path in abspaths:
            remove.append(full_path)
            abspaths.remove(full_path)

        else:
            kept_entries.append(e) # preservee entries

    # if abspathh is empty, it meand soem paths werent in the index
    if len(abspaths) > 0 and not skip_missing:
        raise Exception(f"Cannot remove paths not in the index: {abspaths}")

    # Physically delete paths from filesystem.
    if delete:
        for path in remove:
            os.unlink(path)

    #Update the list of entries in the index ,and write it back
    index.entries = keput_entries
    index_write(repo , index)


argsp = argsubprasers.add_praser("add" , help = "Add files contents to the index.")
argsp.add_argument("path" , args = "+" . help = "Files to add")

def cmd_add(args):
    repo = repo_find()
    add(repo , args.path)

    