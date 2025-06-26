import argparse
import difflib
import os


def sync_files(mdc_path: str, md_path: str, dry_run: bool = False) -> None:
    """
    Synchronizes content from a source .mdc file to a target .md file.
    The content of the .mdc file completely overwrites the .md file.
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

    md_content_original = ""
    original_file_existed = os.path.exists(md_path)
    if original_file_existed:
        try:
            with open(md_path, "r", encoding="utf-8") as md_file:
                md_content_original = md_file.read()
        except Exception as e:
            print(
                f"⚠️ Error reading existing .md file {md_path}: {e} (Treating as new file for sync)"
            )
            original_file_existed = False

    # Normalize line endings for comparison and writing
    new_md_content_normalized = new_md_content.replace("\r\n", "\n").strip()
    md_content_original_normalized = md_content_original.replace("\r\n", "\n")

    if md_content_original_normalized == new_md_content_normalized:
        if original_file_existed:
            print(f"✨ No changes needed for {md_path} (already in sync with {mdc_path})")
        return

    if dry_run:
        operation = "update" if original_file_existed else "create"
        print(f"\n🔍 [{operation.upper()}] Diff for {md_path} (target):")

        fromfile_content = md_content_original_normalized if original_file_existed else ""
        fromfile_label = md_path + (
            " (original)" if original_file_existed else " (as new empty file)"
        )

        diff = difflib.unified_diff(
            fromfile_content.splitlines(keepends=True),
            new_md_content_normalized.splitlines(keepends=True),
            fromfile=fromfile_label,
            tofile=md_path + " (proposed)",
            lineterm="",
        )
        for line in diff:
            print(line, end="")
        if not original_file_existed:
            print(f"ℹ️  Would create {md_path} with content from {mdc_path}")
        else:
            print(f"ℹ️  Would update {md_path} with content from {mdc_path}")

    else:
        action_verb = "Updated" if original_file_existed else "Created"
        try:
            with open(md_path, "w", encoding="utf-8", newline="\n") as md_file_to_write:
                md_file_to_write.write(new_md_content_normalized)
            print(f"✅ {action_verb} {md_path} from {mdc_path}")
        except Exception as e:
            print(f"❌ Error writing to file {md_path}: {e}")


def sync_directory(mdc_dir: str, md_dir: str, dry_run: bool) -> None:
    """
    Synchronizes .md files in md_dir with .mdc files from mdc_dir.
    Creates new .md files, updates existing ones,
    and prunes orphaned .md files.
    """
    print(f"🔄 Starting sync from '{mdc_dir}' to '{md_dir}'...")
    if dry_run:
        print("DRY RUN MODE: No files will be changed on disk.")

    if not os.path.exists(md_dir):
        if dry_run:
            print(f"ℹ️  Target directory '{md_dir}' does not exist. Would create it.")
        else:
            try:
                os.makedirs(md_dir, exist_ok=True)
                print(f"📁 Created target directory '{md_dir}'.")
            except OSError as e:
                print(f"❌ Error creating target directory '{md_dir}': {e}. Aborting sync.")
                return
    elif not os.path.isdir(md_dir):
        print(f"❌ Error: Target path '{md_dir}' exists but is not a directory. Aborting sync.")
        return

    mdc_basenames = set()

    if not os.path.exists(mdc_dir) or not os.path.isdir(mdc_dir):
        print(
            f"⚠️ Source directory '{mdc_dir}' not found or not a directory. "
            f"Will proceed to prune target directory if applicable."
        )
    else:
        print(f"\nProcessing files from '{mdc_dir}':")
        for mdc_filename in sorted(os.listdir(mdc_dir)):
            if mdc_filename.endswith(".mdc"):
                base_name = os.path.splitext(mdc_filename)[0]
                mdc_basenames.add(base_name)
                mdc_path = os.path.join(mdc_dir, mdc_filename)
                md_filename = base_name + ".md"
                md_path = os.path.join(md_dir, md_filename)
                sync_files(mdc_path, md_path, dry_run)

    print(f"\n🔎 Checking for orphaned files in '{md_dir}' to prune...")
    found_orphans_to_prune = 0
    if os.path.isdir(md_dir):
        for md_filename_to_check in sorted(os.listdir(md_dir)):
            if md_filename_to_check.endswith(".md"):
                md_base_name = os.path.splitext(md_filename_to_check)[0]
                if md_base_name not in mdc_basenames:
                    orphaned_md_path = os.path.join(md_dir, md_filename_to_check)
                    found_orphans_to_prune += 1
                    if dry_run:
                        print(f"🗑️ Would delete orphaned file: {orphaned_md_path}")
                    else:
                        try:
                            os.remove(orphaned_md_path)
                            print(f"🗑️ Deleted orphaned file: {orphaned_md_path}")
                        except OSError as e:
                            print(f"❌ Error deleting file '{orphaned_md_path}': {e}")
    else:
        print(f"⚠️ Target directory '{md_dir}' not found. Cannot prune.")

    if found_orphans_to_prune == 0:
        print("👍 No orphaned .md files to prune.")
    else:
        print(f"Total orphaned files processed for pruning: {found_orphans_to_prune}")

    print("\n🏁 Sync process complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Synchronizes .md files from .mdc source files.\n"
            "Key features:\n"
            "- Overwrites target .md files with content from source .mdc files.\n"
            "- Creates new .md files if they don't exist in the target directory.\n"
            "- Deletes (prunes) .md files if their .mdc source is removed.\n"
            "- Creates the target directory if it doesn't exist."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--mdc-dir",
        default=".cursor/rules",
        help="Directory with source .mdc files (default: .cursor/rules)",
    )
    parser.add_argument(
        "--md-dir",
        default=".windsurf/rules",
        help="Directory with target .md files (default: .windsurf/rules)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview all changes (creations, updates, deletions) without modifying the disk.",
    )
    args = parser.parse_args()

    sync_directory(args.mdc_dir, args.md_dir, args.dry_run)
