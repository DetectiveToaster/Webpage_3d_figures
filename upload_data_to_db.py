# batch_upload_by_folder_with_prompt.py

import os
from app.database import SessionLocal
from app import models
from sqlalchemy.orm import Session

DATA_FOLDER = os.path.join(os.path.dirname(__file__), "data")
ALLOWED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".glb"]

def list_products(db: Session):
    products = db.query(models.Product).all()
    print("\nAvailable Products:")
    for p in products:
        print(f"{p.id}: {p.name}")
    print("")
    return {str(p.id): p.name for p in products}

def guess_media_type(filename):
    ext = filename.lower().split('.')[-1]
    if ext == "glb":
        return "model", "model/gltf-binary"
    elif ext in ["jpg", "jpeg"]:
        return "image", "image/jpeg"
    elif ext == "png":
        return "image", "image/png"
    else:
        return None, None

def upload_media(product_id, media_type, content_type, filepath, db):
    filename = os.path.basename(filepath)
    with open(filepath, "rb") as f:
        file_bytes = f.read()
    db_media = models.ProductMedia(
        product_id=product_id,
        media_type=media_type,
        filename=filename,
        content_type=content_type,
        data=file_bytes
    )
    db.add(db_media)
    db.commit()
    db.refresh(db_media)
    print(f"  Uploaded {filename} as {media_type} to product ID {product_id}.")

if __name__ == "__main__":
    db = SessionLocal()
    product_dict = list_products(db)
    db.close()

    # Scan for folders inside the data directory
    folders = [f for f in os.listdir(DATA_FOLDER) if os.path.isdir(os.path.join(DATA_FOLDER, f))]
    if not folders:
        print("No folders found in 'data/'.")
        exit(0)

    db = SessionLocal()
    for folder in folders:
        folder_path = os.path.join(DATA_FOLDER, folder)
        files = [f for f in os.listdir(folder_path)
                 if os.path.isfile(os.path.join(folder_path, f)) and
                 os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS]
        if not files:
            print(f"\nNo valid media files found in '{folder}'. Skipping.")
            continue

        print(f"\n---\nFolder: {folder}")
        print("Files:")
        for filename in files:
            print(f"  {filename}")

        product_dict = list_products(db)
        while True:
            product_id = input(f"Enter the product ID to assign ALL files in '{folder}' to (or blank to skip): ").strip()
            if not product_id:
                print(f"Skipping folder '{folder}'.")
                break
            if product_id in product_dict:
                for filename in files:
                    filepath = os.path.join(folder_path, filename)
                    media_type, content_type = guess_media_type(filename)
                    if not media_type or not content_type:
                        print(f"  Skipping {filename}: unsupported file type.")
                        continue
                    upload_media(int(product_id), media_type, content_type, filepath, db)
                break
            else:
                print(f"Invalid product ID. Please enter a valid product ID.")

    db.close()
    print("\nAll folders processed.")
