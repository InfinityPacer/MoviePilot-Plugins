import copy
import re
import threading
import time
from typing import Any, Dict, List, Optional

import plexapi
import plexapi.utils
import pypinyin
import zhconv
from plexapi.library import LibrarySection

from app.chain.mediaserver import MediaServerChain
from app.chain.tmdb import TmdbChain
from app.core.cache import cache_backend
from app.core.context import MediaInfo
from app.log import logger
from app.plugins import PluginChian
from app.plugins.plexpersonmeta.helper import RatingInfo, cache_with_logging
from app.schemas import MediaPerson, ServiceInfo
from app.schemas.types import MediaType
from app.utils.string import StringUtils

lock = threading.Lock()


class ScrapeHelper:
    timeout: int = 10

    def __init__(self, config: dict, event: threading.Event, chain: PluginChian,
                 service: ServiceInfo, libraries: dict[int, Any]):
        self.tmdb_chain = TmdbChain()
        self.mediaserver_chain = MediaServerChain()
        self.chain = chain
        self.event = event
        self.service = service
        self.plex = service.instance if service else None
        self.libraries = libraries

        if not config:
            return
        self._lock = config.get("lock")
        self._execute_transfer = config.get("execute_transfer")
        self._scrape_type = config.get("scrape_type", "all")
        self._remove_no_zh = config.get("remove_no_zh", False)
        self._douban_scrape = config.get("douban_scrape", True)
        # self._reserve_tag_key = config.get("reserve_tag_key", False)
        try:
            self._delay = int(config.get("delay", 200))
        except ValueError:
            self._delay = 200

    def scrape_rating_items(self, rating_items: list):
        """刮削媒体库中的媒体项"""
        for rating_item in rating_items:
            if self.check_external_interrupt():
                return
            info = self.get_rating_info(item=rating_item)
            if not info or info.type not in ["movie", "show"]:
                continue
            item = {}
            try:
                item = self.fetch_item(rating_key=info.key)
                if not item:
                    continue
                logger.info(f"开始刮削 {info.title} 的演员信息 ...")
                self.scrape_item(item=item)
                logger.info(f"{info.title} 的演员信息刮削完成")
            except Exception as e:
                logger.error(f"媒体项 {info.title} 刮削过程中出现异常，{str(e)}")

            if info.type != "show":
                logger.info(f"<{info.title}> 类型为 {info.type}，非show类型，跳过剧集刮削")
                continue
            logger.info(f"<{info.title}> 类型为 show，准备进行剧集刮削")
            self.scrape_episodes(item=item)

    def scrape_episode_items(self, episode_items: dict):
        """刮削剧集的媒体信息"""
        for parent_key, episodes in episode_items.items():
            if self.check_external_interrupt():
                return
            item = self.fetch_item(rating_key=parent_key)
            if not item:
                continue
            self.scrape_episodes(item=item, episodes=episodes)

    def scrape_episodes(self, item: dict, episodes: Optional[dict] = None):
        """刮削剧集"""
        info = self.get_rating_info(item=item)
        if not info or info.type != "show":
            return

        try:
            # 如果 episodes 为空，这里获取所有的 episodes 进行刮削
            episodes_provided_all = episodes is None
            if episodes_provided_all:
                episodes = self.list_episodes(rating_key=info.key)

            if not episodes:
                logger.info(f"<{info.title}> 没有找到任何剧集信息，取消剧集刮削")
            else:
                if episodes_provided_all:
                    logger.info(
                        f"<{info.title}> 共计 {item.get('childCount', 0)} 季 {len(episodes)} 集，准备进行剧集刮削")
                else:
                    logger.info(f"<{info.title}> 共计 {len(episodes)} 集，准备进行剧集刮削")

            for episode in episodes:
                if self.check_external_interrupt():
                    return
                episode_info = self.get_rating_info(item=episode, parent_item=item)
                if not episode_info or episode_info.type != "episode":
                    continue
                try:
                    episode_item = self.fetch_item(rating_key=episode_info.key)
                    if not episode_item:
                        continue
                    logger.info(f"开始刮削 {episode_info.title} 的演员信息 ...")
                    self.scrape_item(item=episode_item, info=episode_info)
                    logger.info(f"{episode_info.title} 的演员信息刮削完成")
                except Exception as e:
                    logger.error(f"媒体项 {episode_info.title} 刮削过程中出现异常，{str(e)}")
        except Exception as e:
            logger.error(f"媒体项 {info.title} 刮削剧集过程中出现异常，{str(e)}")

    def scrape_item(self, item: dict, info: Optional[RatingInfo] = None):
        """
        刮削媒体服务器中的条目
        """
        if not item:
            return

        if not info:
            info = self.get_rating_info(item=item)

        if not info or not info.tmdbid:
            logger.warning(f"{info.title} 未找到tmdbid，无法识别媒体信息")
            return

        logger.info(f"{info.title} 正在获取 TMDB 媒体信息")
        mediainfo = self.get_tmdb_media(tmdbid=info.tmdbid,
                                        title=info.search_title,
                                        mtype=MediaType.MOVIE if item.get("type") == "movie" else MediaType.TV)
        if not mediainfo:
            logger.warning(f"{info.title} TMDB 未识别到媒体信息")
            return

        try:
            if self.need_trans_actor(item):
                self.update_peoples(item=item, mediainfo=mediainfo, info=info)
            else:
                logger.info(f"{info.title} 的人物信息已是中文，无需更新")
        except Exception as e:
            logger.error(f"{info.title} 更新人物信息时出错：{str(e)}")

    def need_trans_actor(self, item: dict) -> bool:
        """
        是否需要处理人物信息
        """
        actors = item.get("Role", [])
        if not actors:
            return False

        field_to_check = None
        if self._scrape_type == "name":
            field_to_check = "tag"
        elif self._scrape_type == "role":
            field_to_check = "role"

        if field_to_check:
            for actor in actors:
                # 检查特定字段，且字段不能为空
                field_value = actor.get(field_to_check)
                if field_value and not StringUtils.is_chinese(field_value):
                    return True
        else:
            for actor in actors:
                # 刮削为 all 时，检查 tag 和 role 两个字段，且字段不能均为空
                tag_value = actor.get("tag")
                role_value = actor.get("role")
                if (tag_value and not StringUtils.is_chinese(tag_value)) or \
                        (role_value and not StringUtils.is_chinese(role_value)):
                    return True

        return False

    def update_peoples(self, item: dict, mediainfo: MediaInfo, info: Optional[RatingInfo] = None):
        """处理媒体项中的人物信息"""
        """
        item 的数据结构：
        {
            "Director": [{
                "id": 119824,
                "filter": "director=119824",
                "tag": "Christopher Nolan",
                "tagKey": "5d776825880197001ec9038e",
                "thumb": "https://metadata-static.plex.tv/people/5d776825880197001ec9038e.jpg"
            }],
            "Writer": [{
                "id": 119825,
                "filter": "writer=119825",
                "tag": "Christopher Nolan",
                "tagKey": "5d776825880197001ec9038e",
                "thumb": "https://metadata-static.plex.tv/people/5d776825880197001ec9038e.jpg"
            }],
            "Role": [{
                "id": 94414,
                "filter": "actor=94414",
                "tag": "Cillian Murphy",
                "tagKey": "5d776825880197001ec90394",
                "role": "J. Robert Oppenheimer",
                "thumb": "https://metadata-static.plex.tv/e/people/ef539a37a16672a1a8d20f272b338c6b.jpg"
            }, {
                "id": 119826,
                "filter": "actor=119826",
                "tag": "Emily Blunt",
                "tagKey": "5d7768265af944001f1f6689",
                "role": "Kitty Oppenheimer",
                "thumb": "https://metadata-static.plex.tv/7/people/7a290c167719a107b03c15922013d211.jpg"
            }]
        }
        """
        if not mediainfo:
            return

        title = info.title if info and info.title else item.get("title")
        actors = item.get("Role", [])
        trans_actors = []

        # 将 mediainfo.actors 转换为字典，以 original_name、name、alias 和拼音为键
        actor_dict = {}
        for actor in mediainfo.actors:
            name = actor.get("name")
            original_name = actor.get("original_name")
            if name:
                actor_dict[name] = actor
                if StringUtils.is_chinese(name):
                    actor_dict[self.to_pinyin(name)] = actor
            if original_name:
                actor_dict[original_name] = actor
            person_tmdbid = actor.get("id")
            if person_tmdbid:
                logger.info(f"{name} 正在获取 TMDB 人物信息")
                person_detail = self.get_tmdb_person_detail(person_tmdbid=person_tmdbid)
                if person_detail:
                    cn_name = self.get_chinese_name(person=person_detail)
                    if cn_name:
                        actor["name"] = cn_name
                    if person_detail.also_known_as:
                        actor["also_known_as"] = person_detail.also_known_as
                        for alias in person_detail.also_known_as:
                            actor_dict[alias] = actor

        # 使用TMDB信息更新人物
        for actor in actors:
            if self.check_external_interrupt():
                return
            tag_value = actor.get("tag")
            role_value = actor.get("role")
            if not tag_value:
                continue

            # 批量赋值 original_name 属性，以便后续能够拿到原始值，避免翻译不一致时，豆瓣无法正确获取值
            original_actor = actor_dict.get(tag_value)
            if original_actor:
                actor["original_name"] = original_actor.get("original_name")

            if StringUtils.is_chinese(tag_value) and StringUtils.is_chinese(role_value):
                logger.debug(f"{tag_value} 已是中文数据，无需更新")
                trans_actors.append(actor)
                continue
            try:
                trans_actor = self.update_people_by_tmdb(people=actor, people_dict=actor_dict)
                if trans_actor:
                    trans_actors.append(trans_actor)
                else:
                    trans_actors.append(actor)
            except Exception as e:
                logger.error(f"{title} TMDB 更新人物信息失败：{str(e)}")

        # 使用豆瓣信息更新人物
        if self._douban_scrape:
            # 如果全部人物信息都已经是中文数据，无需使用豆瓣信息更新
            if all(StringUtils.is_chinese(actor.get("tag", "")) and StringUtils.is_chinese(actor.get("role", "")) for
                   actor in trans_actors):
                logger.info(f"{title} 的人物信息已是中文，无需使用豆瓣信息更新")
            else:
                # 存在人物信息还不是中文数据，使用豆瓣信息进行更新
                logger.info(f"{title} 正在获取豆瓣媒体信息")
                douban_actors = self.get_douban_actors(imdbid=mediainfo.imdb_id,
                                                       title=mediainfo.title,
                                                       mtype=mediainfo.type,
                                                       year=mediainfo.year,
                                                       season=mediainfo.season,
                                                       season_years=tuple(sorted(mediainfo.season_years.items())))
                if douban_actors:
                    # 将 douban_actors 转换为字典，以 latin_name 和 name 和拼音为键
                    douban_actor_dict = {}
                    for actor in douban_actors:
                        name = actor.get("name")
                        latin_name = actor.get("latin_name")
                        if name:
                            douban_actor_dict[name] = actor
                            if StringUtils.is_chinese(name):
                                douban_actor_dict[self.to_pinyin(name)] = actor
                        if latin_name:
                            douban_actor_dict[latin_name] = actor
                            douban_actor_dict[self.standardize_name_order(latin_name)] = actor

                    for actor in trans_actors:
                        if self.check_external_interrupt():
                            return
                        try:
                            tag_value = actor.get("tag")
                            role_value = actor.get("role")
                            if StringUtils.is_chinese(tag_value) and StringUtils.is_chinese(role_value):
                                logger.debug(f"{tag_value} 已是中文数据，无需使用豆瓣信息更新")
                                continue

                            updated_actor = self.update_people_by_douban(people=actor,
                                                                         people_dict=douban_actor_dict)
                            if updated_actor:
                                actor.update(updated_actor)
                        except Exception as e:
                            logger.error(f"{title} 豆瓣更新人物信息失败：{str(e)}")

        if trans_actors:
            try:
                self.put_actors(item=item, actors=trans_actors)
                logger.info(f"{title} 的中文人物信息更新完成")
            except Exception as e:
                logger.error(f"{title} 的中文人物信息更新失败：{str(e)}")

    def put_actors(self, item: dict, actors: list):
        """更新演员信息"""
        if not item or not actors:
            return

        rating_key = item.get("ratingKey")
        if not rating_key:
            return

        # 创建actors_param字典
        actors_param = {}
        for i, actor in enumerate(actors):
            actor_index = f"actor[{i}]"
            actor_tag_key = actor.get("tagKey", "")

            actors_param.update({
                f"{actor_index}.tag.tag": actor.get("tag", ""),
                f"{actor_index}.tagging.text": actor.get("role", ""),
                f"{actor_index}.tag.thumb": actor.get("thumb", ""),
                f"{actor_index}.tag.tagKey": actor_tag_key
            })

            # if self._reserve_tag_key:
            #     actors_param[f"{actor_index}.tag.art"] = actor_tag_key

        params = {
            "actor.locked": 1 if self._lock else 0
        }
        params.update(actors_param)

        endpoint = f"library/metadata/{rating_key}"
        self.plex.put_data(
            endpoint=endpoint,
            params=params,
            timeout=self.timeout
        )

    def update_people_by_tmdb(self, people: dict, people_dict: dict) -> Optional[dict]:
        """更新人物信息，返回替换后的人物信息"""
        """
        people 的数据结构:
        {
            "id": 94414,
            "filter": "actor=94414",
            "tag": "Cillian Murphy",
            "tagKey": "5d776825880197001ec90394",
            "role": "J. Robert Oppenheimer",
            "thumb": "https://metadata-static.plex.tv/e/people/ef539a37a16672a1a8d20f272b338c6b.jpg"
        }

        people_dict 的数据结构:
        [{
            "adult": False,
            "gender": 2,
            "id": 2037,
            "known_for_department": "Acting",
            "name": "基利安·墨菲",
            "original_name": "Cillian Murphy",
            "popularity": 48.424,
            "profile_path": "/dm6V24NjjvjMiCtbMkc8Y2WPm2e.jpg",
            "cast_id": 3,
            "character": "J. Robert Oppenheimer",
            "credit_id": "613a940d9653f60043e380df",
            "order": 0
        }, {
            "adult": False,
            "gender": 1,
            "id": 5081,
            "known_for_department": "Acting",
            "name": "艾米莉·布朗特",
            "original_name": "Emily Blunt",
            "popularity": 94.51,
            "profile_path": "/5nCSG5TL1bP1geD8aaBfaLnLLCD.jpg",
            "cast_id": 161,
            "character": "Kitty Oppenheimer",
            "credit_id": "6328c918524978007e9f1a7f",
            "order": 1
        }]
        """
        if not people_dict:
            return None

        # 返回的人物信息
        ret_people = copy.deepcopy(people)

        # 查找对应的 TMDB 人物信息
        person_name = people.get("tag")
        person_name_lower = self.remove_spaces_and_lower(person_name)
        person_pinyin = self.to_pinyin(person_name)

        # 构建一个包含所有潜在键的列表后，再进行逐一获取
        potential_keys = [person_name, person_name_lower, person_pinyin]
        person_detail = next((people_dict[key] for key in potential_keys if key in people_dict), None)

        # 从 TMDB 演员中匹配中文名称、角色和简介
        if not person_detail:
            logger.debug(f"人物 {person_name} 未找到中文数据")
            return None

        # 名称
        if StringUtils.is_chinese(person_name):
            logger.debug(f"{person_name} 已是中文名称，无需更新")
        else:
            cn_name = self.get_chinese_field_value(people=person_detail, field="name")
            if cn_name:
                logger.debug(f"{person_name} 从 TMDB 获取到中文名称：{cn_name}")
                ret_people["tag"] = cn_name
            else:
                logger.debug(f"{person_name} 从 TMDB 未能获取到中文名称")

        # 角色
        character = people.get("role")
        if StringUtils.is_chinese(character):
            logger.debug(f"{person_name} 已是中文角色，无需更新")
        else:
            cn_character = self.get_chinese_field_value(people=person_detail, field="character")
            if cn_character:
                logger.debug(f"{person_name} 从 TMDB 获取到中文角色：{cn_character}")
                ret_people["role"] = cn_character
            else:
                logger.debug(f"{person_name} 从 TMDB 未能获取到中文角色")

        return ret_people

    def update_people_by_douban(self, people: dict, people_dict: dict) -> Optional[dict]:
        """从豆瓣信息中更新人物信息"""
        """
        people 的数据结构:
        {
            "id": 94414,
            "filter": "actor=94414",
            "tag": "Cillian Murphy",
            "tagKey": "5d776825880197001ec90394",
            "role": "J. Robert Oppenheimer",
            "thumb": "https://metadata-static.plex.tv/e/people/ef539a37a16672a1a8d20f272b338c6b.jpg"
            "original_name": "Cillian Murphy"
        }

        people_dict 的数据结构
        {
          "name": "丹尼尔·克雷格",
          "roles": [
            "演员",
            "制片人",
            "配音"
          ],
          "title": "丹尼尔·克雷格（同名）英国,英格兰,柴郡,切斯特影视演员",
          "url": "https://movie.douban.com/celebrity/1025175/",
          "user": null,
          "character": "饰 詹姆斯·邦德 James Bond 007",
          "uri": "douban://douban.com/celebrity/1025175?subject_id=27230907",
          "avatar": {
            "large": "https://qnmob3.doubanio.com/view/celebrity/raw/public/p42588.jpg?imageView2/2/q/80/w/600/h/3000/format/webp",
            "normal": "https://qnmob3.doubanio.com/view/celebrity/raw/public/p42588.jpg?imageView2/2/q/80/w/200/h/300/format/webp"
          },
          "sharing_url": "https://www.douban.com/doubanapp/dispatch?uri=/celebrity/1025175/",
          "type": "celebrity",
          "id": "1025175",
          "latin_name": "Daniel Craig"
        }
        """
        if not people_dict:
            return people

        # 返回的人物信息
        ret_people = copy.deepcopy(people)

        # 查找对应的豆瓣人物信息
        person_name = people.get("tag")
        original_name = people.get("original_name")
        also_known_as = people.get("also_known_as", [])
        person_name_lower = self.remove_spaces_and_lower(person_name)
        person_pinyin = self.to_pinyin(person_name)

        # 构建一个包含所有潜在键的列表后，再进行逐一获取
        potential_keys = [person_name, original_name] + also_known_as + [person_name_lower, person_pinyin]
        person_detail = next((people_dict[key] for key in potential_keys if key in people_dict), None)

        # 从豆瓣演员中匹配中文名称、角色和简介
        if not person_detail:
            logger.debug(f"人物 {person_name} 未找到中文数据")
            return None

        # 名称
        if StringUtils.is_chinese(person_name):
            logger.debug(f"{person_name} 已是中文名称，无需更新")
        else:
            cn_name = self.get_chinese_field_value(people=person_detail, field="name")
            if cn_name:
                logger.debug(f"{person_name} 从豆瓣中获取到中文名称：{cn_name}")
                ret_people["tag"] = cn_name
            else:
                logger.debug(f"{person_name} 从豆瓣未能获取到中文名称")

        # 角色
        character = people.get("role")
        if StringUtils.is_chinese(character):
            logger.debug(f"{person_name} 已是中文角色，无需更新")
        else:
            cn_character = self.get_chinese_field_value(people=person_detail, field="character")
            if cn_character:
                # "饰 詹姆斯·邦德 James Bond 007"
                cn_character = re.sub(r"饰\s+", "", cn_character)
                cn_character = re.sub("演员", "", cn_character)
                if cn_character:
                    logger.debug(f"{person_name} 从豆瓣中获取到中文角色：{cn_character}")
                    ret_people["role"] = cn_character
                else:
                    logger.debug(f"{person_name} 从豆瓣未能获取到中文角色")
            else:
                logger.debug(f"{person_name} 从豆瓣未能获取到中文角色")

        return ret_people

    @cache_with_logging("plex_tmdb_person", "PERSON")
    def get_tmdb_person_detail(self,
                               person_tmdbid: int) -> Optional[MediaPerson]:
        """获取TMDB媒体信息"""
        try:
            person_detail = self.tmdb_chain.person_detail(int(person_tmdbid))
            return person_detail
        except Exception as e:
            logger.error(f"{person_tmdbid} TMDB 识别人员信息时出错：{str(e)}")
            return None

    @cache_with_logging("plex_tmdb_media", "TMDB")
    def get_tmdb_media(self,
                       tmdbid: int,
                       title: str,
                       mtype: MediaType = MediaType.TV) -> Optional[MediaInfo]:
        """获取TMDB媒体信息"""
        try:
            mediainfo = self.chain.recognize_media(mtype=mtype, tmdbid=tmdbid)
            return mediainfo
        except Exception as e:
            logger.error(f"{title} TMDB 识别媒体信息时出错：{str(e)}")
            return None

    @cache_with_logging("plex_douban_media", "TMDB")
    def get_douban_actors(self,
                          title: str,
                          imdbid: Optional[str] = None,
                          mtype: Optional[MediaType] = None,
                          year: Optional[str] = None,
                          season: Optional[int] = None,
                          season_years: Any = None) -> List[dict]:
        """获取豆瓣演员信息"""
        douban_actors = []

        if season_years and len(season_years) > 1:
            for season, year in season_years:
                actors = self.fetch_douban_actors(fetch_title=title, fetch_mtype=mtype, fetch_year=year,
                                                  fetch_season=season)
                if actors:
                    douban_actors.extend(actors)
        else:
            actors = self.fetch_douban_actors(fetch_title=title, fetch_imdbid=imdbid, fetch_mtype=mtype,
                                              fetch_year=year,
                                              fetch_season=season)
            if actors:
                douban_actors.extend(actors)

        return douban_actors if douban_actors else None

    def fetch_douban_actors(self, fetch_title: str,
                            fetch_imdbid: Optional[str] = None,
                            fetch_mtype: Optional[MediaType] = None,
                            fetch_year: Optional[str] = None,
                            fetch_season: Optional[int] = None) -> Optional[List[dict]]:
        """
        获取演员信息
        :param fetch_title: 影片标题
        :param fetch_imdbid: IMDB ID，可选
        :param fetch_mtype: 媒体类型，可选
        :param fetch_year: 年份，可选
        :param fetch_season: 季，可选
        :return: 包含演员信息的字典列表，或 None
        """
        try:
            sleep_time = 5 + int(time.time()) % 7
            logger.debug(f"随机休眠 {sleep_time}秒 ...")
            time.sleep(sleep_time)
            doubaninfo = self.chain.match_doubaninfo(name=fetch_title,
                                                     imdbid=fetch_imdbid,
                                                     mtype=fetch_mtype,
                                                     year=fetch_year,
                                                     season=fetch_season,
                                                     raise_exception=True)
            if doubaninfo:
                item = self.chain.douban_info(doubaninfo.get("id"), raise_exception=True) or {}
                if item:
                    return (item.get("actors") or []) + (item.get("directors") or [])
                else:
                    logger.debug(f"未找到豆瓣详情：{fetch_title}({fetch_year})")
                    return None
            else:
                logger.debug(f"未找到豆瓣信息：{fetch_title}({fetch_year})")
                return None
        except Exception as e:
            logger.error(f"{fetch_title} 豆瓣识别媒体信息时出错：{str(e)}")
            return None

    @staticmethod
    def get_chinese_name(person: MediaPerson) -> Optional[str]:
        """
        获取TMDB别名中的中文名
        """
        try:
            # 如果人物名称已经是中文，则直接返回，不再繁简转换
            if StringUtils.is_chinese(person.name):
                return person.name
            also_known_as = person.also_known_as or []
            if also_known_as:
                for name in also_known_as:
                    if name and StringUtils.is_chinese(name):
                        # 使用cn2an将繁体转化为简体
                        return zhconv.convert(name, "zh-hans")
        except Exception as err:
            logger.error(f"获取人物中文名失败：{err}")
        return None

    @staticmethod
    def get_chinese_field_value(people: dict, field: str) -> Optional[str]:
        """
        获取TMDB的中文名称
        """
        """
        people 的数据结构
        {
            "adult": False,
            "gender": 2,
            "id": 2037,
            "known_for_department": "Acting",
            "name": "基利安·墨菲",
            "original_name": "Cillian Murphy",
            "popularity": 48.424,
            "profile_path": "/dm6V24NjjvjMiCtbMkc8Y2WPm2e.jpg",
            "cast_id": 3,
            "character": "J. Robert Oppenheimer",
            "credit_id": "613a940d9653f60043e380df",
            "order": 0
        }
        """
        try:
            field_value = people.get(field, "")
            if field_value and StringUtils.is_chinese(field_value):
                return field_value
        except Exception as e:
            logger.error(f"获取人物{field}失败：{e}")
        return None

    @staticmethod
    def get_season_episode(item: Dict) -> str:
        """获取剧集的季和集信息"""
        season_number = item.get("parentIndex", "0")
        episode_number = item.get("index", "0")
        return f"s{str(season_number).zfill(2)}e{str(episode_number).zfill(2)}"

    @staticmethod
    def get_rating_info(item: dict, parent_item: Optional[dict] = None) -> Optional[RatingInfo]:
        """获取媒体项目信息"""
        if not item:
            return None

        key = item.get("ratingKey")
        if not key:
            return None

        rating_type = item.get("type")
        title = item.get("title", key)
        search_title = title

        # 获取 TMDB ID
        tmdbid = (ScrapeHelper.get_tmdb_id(item=parent_item) if parent_item
                  else ScrapeHelper.get_tmdb_id(item=item))

        # 如果是剧集，调整标题格式
        if rating_type == "episode":
            parent_title = parent_item.get("title") if parent_item else item.get("grandparentTitle", title)
            title = f"{parent_title} - {ScrapeHelper.get_season_episode(item=item)} - {title}"
            search_title = parent_title

        return RatingInfo(key=key,
                          type=rating_type,
                          title=title,
                          search_title=search_title,
                          tmdbid=tmdbid)

    def list_rating_items(self, library: LibrarySection):
        """获取所有媒体项目"""
        if not library:
            return []

        endpoint = f"/library/sections/{library.key}/all?type={plexapi.utils.searchType(libtype=library.TYPE)}"

        response = self.plex.get_data(endpoint=endpoint, timeout=self.timeout)
        datas = (response
                 .json()
                 .get("MediaContainer", {})
                 .get("Metadata", []))

        if len(datas):
            logger.info(f"<{library.title} {library.TYPE}> "
                        f"类型共计 {len(datas)} 个")

        return datas

    def list_rating_items_by_added(self, added_time: int):
        """获取最近入库媒体"""
        endpoint = f"/library/all?addedAt>={added_time}"
        response = self.plex.get_data(endpoint=endpoint, timeout=self.timeout)
        datas = (response
                 .json()
                 .get("MediaContainer", {})
                 .get("Metadata", []))
        return datas

    def list_episodes(self, rating_key, ):
        """获取show的所有剧集"""
        endpoint = f"/library/metadata/{rating_key}/allLeaves"

        response = self.plex.get_data(endpoint=endpoint, timeout=self.timeout)
        datas = (response
                 .json()
                 .get("MediaContainer", {})
                 .get("Metadata", []))

        return datas

    def fetch_item(self, rating_key):
        """
        获取条目信息
        """
        endpoint = f"/library/metadata/{rating_key}"
        response = self.plex.get_data(endpoint=endpoint, timeout=self.timeout)
        datas = (response
                 .json()
                 .get("MediaContainer", {})
                 .get("Metadata", []))
        return datas[0] if datas else None

    def fetch_all_items(self, rating_keys):
        """
        批量获取条目。
        :param rating_keys: 需要获取的条目的评级键列表。
        :return: 获取的所有条目列表。
        """
        endpoint = f"/library/metadata/{','.join(rating_keys)}"
        response = self.plex.get_data(endpoint=endpoint, timeout=self.timeout)
        items = (response
                 .json()
                 .get("MediaContainer", {})
                 .get("Metadata", []))
        return items

    @staticmethod
    def get_tmdb_id(item) -> Optional[int]:
        """获取 tmdb_id"""
        if not item:
            return None
        guids = item.get("Guid", [])
        if not guids:
            return None
        for guid in guids:
            guid_id = guid.get("id", "")
            if guid_id.startswith("tmdb://"):
                parts = guid_id.split("tmdb://")
                if len(parts) == 2 and parts[1].isdigit():
                    return int(parts[1])
        return None

    def check_external_interrupt(self, service: Optional[str] = None) -> bool:
        """
        检查是否有外部中断请求，并记录相应的日志信息
        """
        if self.event.is_set():
            logger.warning(f"外部中断请求，{service if service else 'Plex演职人员刮削'} 服务停止")
            return True
        return False

    @staticmethod
    def to_pinyin(string) -> str:
        """将中文字符串转换为拼音，没有空格分隔"""
        return pypinyin.slug(string, separator="", style=pypinyin.Style.NORMAL, strict=False).lower()

    @staticmethod
    def standardize_name_order(name) -> str:
        """将英文名标准化为统一的顺序（姓在前，名在后）"""
        parts = name.split()
        if len(parts) == 2:
            return f"{parts[1]} {parts[0]}"
        return name

    @staticmethod
    def remove_spaces_and_lower(string) -> str:
        """去除字符串中的空格并转换为小写"""
        return string.replace(" ", "").lower()

    @staticmethod
    def extract_key_from_url(url: str) -> Optional[str]:
        """从URL中提取key"""
        match = re.search(r'/library/metadata/(\d+)', url)
        return match.group(1) if match else None

    @staticmethod
    def clear_cache():
        """
        清理缓存
        """
        cache_backend.clear(region="plex_tmdb_media")
        cache_backend.clear(region="plex_tmdb_person")
        cache_backend.clear(region="plex_douban_media")
