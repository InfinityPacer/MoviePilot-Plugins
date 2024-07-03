-- 删除之前可能存在的同名触发器
DROP TRIGGER IF EXISTS after_insert_tags_for_plexpersonmeta;

-- 创建一个条件性的 AFTER INSERT 触发器
CREATE TRIGGER after_insert_tags_for_plexpersonmeta
AFTER INSERT ON tags
WHEN NEW.tag_type = 6 
    AND COALESCE(NEW.user_art_url, '') != '' 
    AND COALESCE(NEW.key, '') = '' 
    AND NOT EXISTS (
        SELECT 1 
        FROM tags 
        WHERE tag_type = 6 
        AND tag = NEW.tag 
        AND key = NEW.user_art_url
    )
BEGIN
    -- 插入新的记录到 tags 表中
    INSERT INTO tags (
        metadata_item_id,
        tag,
        tag_type,
        user_thumb_url,
        user_art_url,
        user_music_url,
        created_at,
        updated_at,
        tag_value,
        extra_data,
        key,
        parent_id
    ) VALUES (
        NEW.metadata_item_id,
        NEW.tag,
        NEW.tag_type,
        NEW.user_thumb_url,
        NEW.user_art_url,
        NEW.user_music_url,
        NEW.created_at,
        NEW.updated_at,
        NEW.tag_value,
        NEW.extra_data,
        NEW.user_art_url,  -- 请注意这里的 key 字段用的是 user_art_url
        NEW.parent_id
    );
END;

-- 删除之前可能存在的同名触发器
DROP TRIGGER IF EXISTS after_update_tags_for_plexpersonmeta;

-- 创建一个条件性的 AFTER UPDATE 触发器
CREATE TRIGGER after_update_tags_for_plexpersonmeta
AFTER UPDATE ON tags
WHEN NEW.tag_type = 6 
    AND COALESCE(NEW.user_art_url, '') != '' 
    AND COALESCE(NEW.key, '') = '' 
BEGIN
    -- 尝试更新记录
    UPDATE tags
    SET
        metadata_item_id = NEW.metadata_item_id,
        tag = NEW.tag,
        user_thumb_url = NEW.user_thumb_url,
        user_art_url = NEW.user_art_url,
        user_music_url = NEW.user_music_url,
        created_at = NEW.created_at,
        updated_at = NEW.updated_at,
        tag_value = NEW.tag_value,
        extra_data = NEW.extra_data,
        parent_id = NEW.parent_id
    WHERE 
        tag_type = 6
        AND tag = NEW.tag
        AND key = NEW.user_art_url;

    -- 如果没有更新到任何记录，执行插入
    INSERT INTO tags (
        metadata_item_id,
        tag,
        tag_type,
        user_thumb_url,
        user_art_url,
        user_music_url,
        created_at,
        updated_at,
        tag_value,
        extra_data,
        key,
        parent_id
    )
    SELECT
        NEW.metadata_item_id,
        NEW.tag,
        NEW.tag_type,
        NEW.user_thumb_url,
        NEW.user_art_url,
        NEW.user_music_url,
        NEW.created_at,
        NEW.updated_at,
        NEW.tag_value,
        NEW.extra_data,
        NEW.user_art_url,
        NEW.parent_id
    WHERE NOT EXISTS (
        SELECT 1 FROM tags 
        WHERE tag_type = 6 AND tag = NEW.tag AND key = NEW.user_art_url
    );
END;

-- 删除之前可能存在的同名触发器
DROP TRIGGER IF EXISTS after_delete_tags_for_plexpersonmeta;

-- 创建 AFTER DELETE 触发器
CREATE TRIGGER after_delete_tags_for_plexpersonmeta
AFTER DELETE ON tags
WHEN OLD.tag_type = 6
BEGIN
    -- 删除 tagging 表中所有与被删除记录具有相同 'tag' 且 tag_type = 6 的记录对应的 tag_id
    DELETE FROM taggings
    WHERE tag_id IN (
        SELECT id FROM tags WHERE tag = OLD.tag AND tag_type = 6
    );

    -- 删除所有具有与被删除记录相同 'tag' 且 tag_type = 6 的记录
    DELETE FROM tags
    WHERE tag = OLD.tag AND tag_type = 6;
END;

-- 删除之前可能存在的同名触发器
DROP TRIGGER IF EXISTS after_insert_taggings_for_plexpersonmeta;

-- 删除之前可能存在的同名触发器
DROP TRIGGER IF EXISTS after_insert_taggings_for_plexpersonmeta;

-- 创建 AFTER INSERT 触发器
CREATE TRIGGER after_insert_taggings_for_plexpersonmeta
AFTER INSERT ON taggings
WHEN NEW.tag_id IN (SELECT id FROM tags WHERE tag_type = 6 AND COALESCE(key, '') = '')
BEGIN
    -- 更新 taggings 表，设置 tag_id 为 tags 表中最新的且 key 不为空的记录的 id
    UPDATE taggings
    SET tag_id = (
        SELECT id FROM tags
        WHERE tag = (SELECT tag FROM tags WHERE id = NEW.tag_id)
        AND tag_type = 6
        AND COALESCE(key, '') != ''
        ORDER BY id DESC
        LIMIT 1
    )
    WHERE id = NEW.id
    AND (
        SELECT id FROM tags
        WHERE tag = (SELECT tag FROM tags WHERE id = NEW.tag_id)
        AND tag_type = 6
        AND COALESCE(key, '') != ''
        ORDER BY id DESC
        LIMIT 1
    ) IS NOT NULL;
END;

-- 删除之前可能存在的同名触发器
DROP TRIGGER IF EXISTS after_update_taggings_for_plexpersonmeta;

-- 创建 AFTER UPDATE 触发器
CREATE TRIGGER after_update_taggings_for_plexpersonmeta
AFTER UPDATE ON taggings
WHEN NEW.tag_id IN (SELECT id FROM tags WHERE tag_type = 6 AND COALESCE(key, '') = '')
BEGIN
    -- 更新 taggings 表，设置 tag_id 为 tags 表中最新的且 key 不为空的记录的 id
    UPDATE taggings
    SET tag_id = (
        SELECT id FROM tags
        WHERE tag = (SELECT tag FROM tags WHERE id = NEW.tag_id)
        AND tag_type = 6
        AND COALESCE(key, '') != ''
        ORDER BY id DESC
        LIMIT 1
    )
    WHERE id = NEW.id
    AND (
        SELECT id FROM tags
        WHERE tag = (SELECT tag FROM tags WHERE id = NEW.tag_id)
        AND tag_type = 6
        AND COALESCE(key, '') != ''
        ORDER BY id DESC
        LIMIT 1
    ) IS NOT NULL;
END;
