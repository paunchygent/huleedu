import argparse
import os


def sync_files(source_path: str, target_path: str) -> None:
    """
    Synchronizes content from a source .md file to a target .md file,
    ensuring the target is perfectly formatted for pre-commit hooks.
    """
    try:
        with open(source_path, "r", encoding="utf-8") as source_file:
            new_md_content = source_file.read()
    except FileNotFoundError:
        print(f"⚠️ Error: Source .md file not found: {source_path} (Skipping)")
        return
    except Exception as e:
        print(f"⚠️ Error reading .md file {source_path}: {e} (Skipping)")
        return

    new_md_content_normalized = new_md_content.rstrip()
    # If the content is not empty after stripping, add exactly one newline.
    if new_md_content_normalized:
        new_md_content_normalized += "\n"

    target_content_original = ""
    original_file_existed = os.path.exists(target_path)
    if original_file_existed:
        try:
            with open(target_path, "r", encoding="utf-8") as target_file:
                target_content_original = target_file.read()
        except Exception as e:
            print(f"⚠️ Error reading existing .md file {target_path}: {e}")
            # Force a write by making the original content different
            target_content_original = "<read_error>"

    # Unconditionally write the canonical content to disk to ensure that
    # what the next hook sees is exactly what this script produces.
    has_changed = target_content_original != new_md_content_normalized
    action_verb = "Updated" if original_file_existed else "Created"
    try:
        with open(target_path, "w", encoding="utf-8", newline="\n") as target_file_to_write:
            target_file_to_write.write(new_md_content_normalized)
        if has_changed:
            print(f"✅ {action_verb} {target_path} from {source_path}")
        else:
            # The file was already perfect, but we're re-writing to be certain.
            print(f"✨ Verified {target_path} (already perfect)")
    except Exception as e:
        print(f"❌ Error writing to file {target_path}: {e}")


def sync_directory(source_dir: str, target_dir: str) -> None:
    """
    Synchronizes .md files in target_dir with .md files from source_dir.
    Creates new .md files, updates existing ones, and prunes orphaned .md files.
    """
    print(f"🔄 Starting sync from '{source_dir}' to '{target_dir}'...")

    if not os.path.exists(target_dir):
        try:
            os.makedirs(target_dir, exist_ok=True)
            print(f"📁 Created target directory '{target_dir}'.")
        except OSError as e:
            print(f"❌ Error creating target directory '{target_dir}': {e}. Aborting sync.")
            return
    elif not os.path.isdir(target_dir):
        print(f"❌ Error: Target path '{target_dir}' exists but is not a directory. Aborting sync.")
        return

    print(f"\nProcessing files from '{source_dir}':")
    expected_md_files = set()
    if not os.path.isdir(source_dir):
        print(f"⚠️ Source directory '{source_dir}' not found. Cannot sync files.")
    else:
        for source_filename in sorted(os.listdir(source_dir)):
            if source_filename.endswith(".md"):
                target_filename = source_filename
                expected_md_files.add(target_filename)
                source_path = os.path.join(source_dir, source_filename)
                target_path = os.path.join(target_dir, target_filename)
                sync_files(source_path, target_path)

    print(f"\n🔎 Checking for orphaned files in '{target_dir}' to prune...")
    try:
        existing_md_files = {f for f in os.listdir(target_dir) if f.endswith(".md")}
        orphaned_files = existing_md_files - expected_md_files

        if orphaned_files:
            for orphan in sorted(list(orphaned_files)):
                try:
                    os.remove(os.path.join(target_dir, orphan))
                    print(f"🗑️  Pruned orphaned file: {orphan}")
                except OSError as e:
                    print(f"❌ Error pruning file {orphan}: {e}")
        else:
            print("👍 No orphaned .md files to prune.")
    except FileNotFoundError:
        print(f"👍 Target directory '{target_dir}' does not exist. No orphans to prune.")

    print("\n🏁 Sync process complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Synchronize .md files from a source .md directory.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--source",
        dest="source_dir",
        default=".claude/rules",
        help="Directory with source .md files (default: .claude/rules)",
    )
    parser.add_argument(
        "--target",
        dest="target_dir",
        default=".windsurf/rules",
        help="Directory with target .md files (default: .windsurf/rules)",
    )

    args, _ = parser.parse_known_args()

    sync_directory(args.source_dir, args.target_dir)
