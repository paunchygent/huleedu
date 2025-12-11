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
    Recursively synchronizes .md files in target_dir with .md files from source_dir.
    Creates new .md files, updates existing ones, and prunes orphaned .md files.
    Handles subdirectories (e.g., core/, backend/, frontend/).
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

    if not os.path.isdir(source_dir):
        print(f"⚠️ Source directory '{source_dir}' not found. Cannot sync files.")
        return

    # Track all expected paths (relative to target_dir) for pruning
    expected_paths: set[str] = set()

    print(f"\nProcessing files from '{source_dir}':")

    for root, dirs, files in os.walk(source_dir):
        # Calculate relative path from source_dir
        rel_path = os.path.relpath(root, source_dir)
        if rel_path == ".":
            rel_path = ""

        # Create corresponding target subdirectory
        if rel_path:
            target_subdir = os.path.join(target_dir, rel_path)
            expected_paths.add(rel_path)
        else:
            target_subdir = target_dir

        if not os.path.exists(target_subdir):
            os.makedirs(target_subdir, exist_ok=True)
            print(f"📁 Created subdirectory '{target_subdir}'")

        # Sync .md files
        for filename in sorted(files):
            if filename.endswith(".md"):
                source_path = os.path.join(root, filename)
                target_path = os.path.join(target_subdir, filename)
                rel_file_path = os.path.join(rel_path, filename) if rel_path else filename
                expected_paths.add(rel_file_path)
                sync_files(source_path, target_path)

    # Prune orphaned files and directories
    print(f"\n🔎 Checking for orphaned files in '{target_dir}' to prune...")
    pruned_any = False

    for root, dirs, files in os.walk(target_dir, topdown=False):
        rel_path = os.path.relpath(root, target_dir)
        if rel_path == ".":
            rel_path = ""

        # Prune orphaned .md files
        for filename in files:
            if filename.endswith(".md"):
                rel_file_path = os.path.join(rel_path, filename) if rel_path else filename
                if rel_file_path not in expected_paths:
                    try:
                        os.remove(os.path.join(root, filename))
                        print(f"🗑️  Pruned orphaned file: {rel_file_path}")
                        pruned_any = True
                    except OSError as e:
                        print(f"❌ Error pruning file {rel_file_path}: {e}")

        # Prune empty directories (except target_dir itself)
        if rel_path and not os.listdir(root):
            try:
                os.rmdir(root)
                print(f"�️  Pruned empty directory: {rel_path}")
                pruned_any = True
            except OSError as e:
                print(f"❌ Error pruning directory {rel_path}: {e}")

    if not pruned_any:
        print("👍 No orphaned files or directories to prune.")

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
