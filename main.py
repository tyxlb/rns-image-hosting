import RNS
import LXMF
import rns_page_node
from PIL import Image
from pathlib import Path
from io import BytesIO
import hashlib
import threading
import time


display_name = "rns-image-hosting"
announce_interval = 20
configpath = "./config"
pagespath = "./pages"
filespath = "./files"
identitypath = configpath + "/identity"
MAX_SIZE = 1_000_000

Path(configpath).mkdir(parents=True, exist_ok=True)
Path(pagespath).mkdir(parents=True, exist_ok=True)
Path(filespath).mkdir(parents=True, exist_ok=True)

if Path(identitypath).is_file():
    identity = RNS.Identity.from_file(identitypath)
    RNS.log("Loaded identity from file", RNS.LOG_INFO)
else:
    RNS.log("No Primary Identity file found, creating new...", RNS.LOG_INFO)
    identity = RNS.Identity()
    identity.to_file(identitypath)


def lxmf_delivery(message: LXMF.LXMessage):
    def process():
        try:
            if LXMF.FIELD_IMAGE not in message.fields:
                return "Failed: No image found"
            # image_type = message.fields[LXMF.FIELD_IMAGE][0]
            image_bytes = BytesIO(message.fields[LXMF.FIELD_IMAGE][1])

            image = Image.open(image_bytes)
            buf = BytesIO()
            image.save(buf, format="WEBP", lossless=True)
            webp_bytes = buf.getvalue()

            if len(webp_bytes) > MAX_SIZE:
                return "Failed: Image is too large"

            webp_hash = hashlib.sha256(webp_bytes).hexdigest()
            output_path = f"{filespath}/{webp_hash}.webp"
            with open(output_path, "wb") as f:
                f.write(webp_bytes)
            request_path = f"/file/{webp_hash}.webp"
            pagenode.destination.register_request_handler(
                request_path,
                response_generator=pagenode.serve_file,
                allow=RNS.Destination.ALLOW_ALL,
                auto_compress=32_000_000,
            )
            return f"Successed: {pagenode_addr[1:-1]}:{request_path}"
        except Exception as e:
            return f"Failed: {str(e)}"

    source = local_lxmf_destination
    dest = message.source
    content = process()
    lxm = LXMF.LXMessage(dest, source, content, None)
    message_router.handle_outbound(lxm)


reticulum = RNS.Reticulum()
pagenode = rns_page_node.PageNode(
    identity=identity,
    pagespath=pagespath,
    filespath=filespath,
    announce_interval=announce_interval,
    name=display_name,
)
pagenode_addr = RNS.prettyhexrep(pagenode.destination.hash)
RNS.log(f"Node address: {pagenode_addr}", RNS.LOG_INFO)
message_router = LXMF.LXMRouter(identity=identity, storagepath=configpath)
local_lxmf_destination = message_router.register_delivery_identity(
    identity=identity, display_name=display_name, stamp_cost=8
)
message_router.register_delivery_callback(lxmf_delivery)
lxmf_addr = RNS.prettyhexrep(local_lxmf_destination.hash)
RNS.log(f"LXMF address: {lxmf_addr}", RNS.LOG_INFO)


def announce():
    local_lxmf_destination.announce()
    schedule_next_run()


def schedule_next_run():
    timer = threading.Timer(announce_interval * 60, announce)
    timer.daemon = True
    timer.start()


announce()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    RNS.log("Keyboard interrupt received, shutting down...", RNS.LOG_INFO)
    pagenode.shutdown()
