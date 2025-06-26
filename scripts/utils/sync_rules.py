import argparse
import os


def sync_files(mdc_path: str, md_path: str) -> None:
    """
    Synchronizes content from a source .mdc file to a target .md file,
    ensuring the target is perfectly formatted for pre-commit hooks.
    """
    try:
        with open(mdc_path, "r", encoding="utf-8") as mdc_file:
            new_md_content = mdc_file.read()
    except FileNotFoundError:
        print(f"⚠️ Error: Source .mdc file not found: {mdc_path} (Skipping)")
        return
    except Exception as e:
        print(f"⚠️ Error reading .mdc file {mdc_path}: {e} (Skipping)")
        return

    # A simpler, more robust normalization logic.
    # First, strip all trailing whitespace including newlines from the entire content.
    new_md_content_normalized = new_md_content.rstrip()
    # If the content is not empty after stripping, add exactly one newline.
    if new_md_content_normalized:
        new_md_content_normalized += "\n"

    md_content_original = ""
    original_file_existed = os.path.exists(md_path)
    if original_file_existed:
        try:
            with open(md_path, "r", encoding="utf-8") as md_file:
                md_content_original = md_file.read()
        except Exception as e:
            print(f"⚠️ Error reading existing .md file {md_path}: {e}")
            # Force a write by making the original content different
            md_content_original = "<read_error>"

    # Unconditionally write the canonical content to disk to ensure that
    # what the next hook sees is exactly what this script produces.
    has_changed = md_content_original != new_md_content_normalized
    action_verb = "Updated" if original_file_existed else "Created"
    try:
        with open(md_path, "w", encoding="utf-8", newline="\n") as md_file_to_write:
            md_file_to_write.write(new_md_content_normalized)
        if has_changed:
            print(f"✅ {action_verb} {md_path} from {mdc_path}")
        else:
            # The file was already perfect, but we're re-writing to be certain.
            print(f"✨ Verified {md_path} (already perfect)")
    except Exception as e:
        print(f"❌ Error writing to file {md_path}: {e}")


def sync_directory(mdc_dir: str, md_dir: str) -> None:
    """
    Synchronizes .md files in md_dir with .mdc files from mdc_dir.
    Creates new .md files, updates existing ones, and prunes orphaned .md files.
    """
    print(f"🔄 Starting sync from '{mdc_dir}' to '{md_dir}'...")

    if not os.path.exists(md_dir):
        try:
            os.makedirs(md_dir, exist_ok=True)
            print(f"📁 Created target directory '{md_dir}'.")
        except OSError as e:
            print(f"❌ Error creating target directory '{md_dir}': {e}. Aborting sync.")
            return
    elif not os.path.isdir(md_dir):
        print(f"❌ Error: Target path '{md_dir}' exists but is not a directory. Aborting sync.")
        return

    print(f"\nProcessing files from '{mdc_dir}':")
    expected_md_files = set()
    if not os.path.isdir(mdc_dir):
        print(f"⚠️ Source directory '{mdc_dir}' not found. Cannot sync files.")
    else:
        for mdc_filename in sorted(os.listdir(mdc_dir)):
            if mdc_filename.endswith(".mdc"):
                md_filename = mdc_filename.replace(".mdc", ".md")
                expected_md_files.add(md_filename)
                mdc_path = os.path.join(mdc_dir, mdc_filename)
                md_path = os.path.join(md_dir, md_filename)
                sync_files(mdc_path, md_path)

    print(f"\n🔎 Checking for orphaned files in '{md_dir}' to prune...")
    try:
        existing_md_files = {f for f in os.listdir(md_dir) if f.endswith(".md")}
        orphaned_files = existing_md_files - expected_md_files

        if orphaned_files:
            for orphan in sorted(list(orphaned_files)):
                try:
                    os.remove(os.path.join(md_dir, orphan))
                    print(f"🗑️  Pruned orphaned file: {orphan}")
                except OSError as e:
                    print(f"❌ Error pruning file {orphan}: {e}")
        else:
            print("👍 No orphaned .md files to prune.")
    except FileNotFoundError:
        print(f"👍 Target directory '{md_dir}' does not exist. No orphans to prune.")

    print("\n🏁 Sync process complete.")


# Trivial change to trigger commit hook
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Synchronize .md files from a source .mdc directory.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--source",
        dest="mdc_dir",
        default=".cursor/rules",
        help="Directory with source .mdc files (default: .cursor/rules)",
    )
    parser.add_argument(
        "--target",
        dest="md_dir",
        default=".windsurf/rules",
        help="Directory with target .md files (default: .windsurf/rules)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Accepts --dry-run for pre-commit compatibility, but the flag is ignored.",
    )
    args = parser.parse_args()

    sync_directory(args.mdc_dir, args.md_dir)
